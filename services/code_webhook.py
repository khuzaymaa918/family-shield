"""Receives what the student enters on the keypad during the Family Shield call. Owner: Teammate A (P2).

The Cartesia call agent sends two things here through its webhook tools:
  1. verify_code: the 4-digit check code
  2. confirm_sent: the answer to "Did you send your family a message asking for money?" (1 yes, 2 no)
This module only receives them; whoever starts it decides what they mean (the Verifier agent).

Inside the Verifier agent:

    from services.code_webhook import ASK, RECORDED, RETRY, start_in_background

    async def on_code(case_id: str, digits: str) -> str:
        #   right code -> return ASK (the call then asks "did you send that message?")
        #   wrong code -> return RETRY once, then RECORDED (call ends, case not confirmed)
        ...

    async def on_answer(case_id: str, answer: str) -> str:   # answer is "yes", "no" or ""
        ...                                                  # tell the Guardian, return RECORDED

    @agent.on_event("startup")
    async def start_code_webhook(ctx):
        start_in_background(on_code, on_answer)

Return fast: the call agent waits on each reply. Do slow work (ctx.send to the Guardian) in
asyncio.create_task(...). If a handler raises or takes longer than HANDLER_TIMEOUT_SECS, the student
hears the safe reply (RECORDED) and the error is logged.

Standalone test (no agents): python -m services.code_webhook
"""
import asyncio
import hmac
import inspect
import logging
import os
import unicodedata
from typing import Awaitable, Callable

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

load_dotenv()
CODE_WEBHOOK_SECRET = os.getenv("CODE_WEBHOOK_SECRET")
CODE_WEBHOOK_PORT = int(os.getenv("CODE_WEBHOOK_PORT") or "8090")

# What the call agent hears back. Its instructions say: "recorded" means thank them and hang up,
# "retry" means ask once more. It never learns whether the code was right.
RECORDED = "recorded"
RETRY = "retry"
ASK = "ask"  # right code: now ask "did you send that message?"
# Cartesia's tool timeout is 10s (cartesia_setup.py). Answer well before it so the agent never improvises.
HANDLER_TIMEOUT_SECS = 5

log = logging.getLogger(__name__)

CodeHandler = Callable[[str, str], str | Awaitable[str]]
AnswerHandler = Callable[[str, str], str | Awaitable[str]]


class CodeIn(BaseModel):
    # The LLM may send the code as a number; accept it rather than failing the tool call.
    model_config = ConfigDict(coerce_numbers_to_str=True)
    case_id: str | None = ""
    code: str


class AnswerIn(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
    case_id: str | None = ""
    answer: str


def _yes_no(text: str) -> str:
    """'1'/'yes' -> 'yes', '2'/'no' -> 'no', anything else -> ''."""
    t = text.strip().lower()
    digits = _digits(t)
    if digits[:1] == "1" or t.startswith("y") or t == "one":
        return "yes"
    if digits[:1] == "2" or t.startswith("n") or t == "two":
        return "no"
    return ""


def _digits(text: str) -> str:
    # Keypad gives 0-9; speech-to-text may give other scripts (e.g. Devanagari), so map every digit to 0-9.
    return "".join(str(unicodedata.digit(ch)) for ch in text if unicodedata.digit(ch, None) is not None)


def _check_auth(authorization: str | None) -> None:
    expected = f"Bearer {CODE_WEBHOOK_SECRET}"
    if not CODE_WEBHOOK_SECRET or not hmac.compare_digest((authorization or "").encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="unauthorized")


async def _call(handler, case_id: str, value: str, what: str) -> str:
    try:
        reply = handler(case_id, value)
        if inspect.isawaitable(reply):
            reply = await asyncio.wait_for(reply, HANDLER_TIMEOUT_SECS)
        return reply
    except Exception as error:
        # Never let a handler failure change what the student hears. Log the type only, never the digits.
        log.error("%s handler failed for case %s: %s", what, case_id or "-", type(error).__name__)
        return RECORDED


def make_app(on_code: CodeHandler, on_answer: AnswerHandler | None = None) -> FastAPI:
    app = FastAPI(title="Family Shield code webhook")

    @app.post("/tools/verify_code")
    async def verify_code(body: CodeIn, authorization: str | None = Header(default=None)) -> dict:
        _check_auth(authorization)
        reply = await _call(on_code, body.case_id or "", _digits(body.code), "code")
        return {"result": reply if reply in (RECORDED, RETRY, ASK) else RECORDED}

    @app.post("/tools/confirm_sent")
    async def confirm_sent(body: AnswerIn, authorization: str | None = Header(default=None)) -> dict:
        _check_auth(authorization)
        if on_answer is None:
            return {"result": RECORDED}
        await _call(on_answer, body.case_id or "", _yes_no(body.answer), "answer")
        return {"result": RECORDED}

    return app


async def serve(on_code: CodeHandler, port: int = CODE_WEBHOOK_PORT, on_answer: AnswerHandler | None = None) -> None:
    """Runs the webhook server in the current event loop until cancelled."""
    if not CODE_WEBHOOK_SECRET:
        raise RuntimeError("Set CODE_WEBHOOK_SECRET in .env")
    # Loopback only: cloudflared forwards from localhost, so nothing on the venue Wi-Fi can reach it directly.
    config = uvicorn.Config(make_app(on_code, on_answer), host="127.0.0.1", port=port, log_level="warning")
    try:
        await uvicorn.Server(config).serve()
    except SystemExit as error:
        # uvicorn calls sys.exit when the port is taken; inside a task that would kill the whole agent.
        raise RuntimeError(f"Code webhook could not start on port {port} (already in use?)") from error


_tasks: set[asyncio.Task] = set()


def start_in_background(on_code: CodeHandler, on_answer: AnswerHandler | None = None,
                        port: int = CODE_WEBHOOK_PORT) -> asyncio.Task:
    """Starts serve() as a task in the running loop. Fails now if the secret is missing; logs later failures."""
    if not CODE_WEBHOOK_SECRET:
        raise RuntimeError("Set CODE_WEBHOOK_SECRET in .env")
    task = asyncio.get_running_loop().create_task(serve(on_code, port, on_answer))
    _tasks.add(task)

    def _report(done: asyncio.Task) -> None:
        _tasks.discard(done)
        if not done.cancelled() and done.exception():
            log.error("Code webhook stopped: %s", done.exception())

    task.add_done_callback(_report)
    return task


if __name__ == "__main__":
    # Test handlers: right code = TEST_CHECK_CODE (default 2580). Prints only outcomes, never the digits.
    normal_code = os.getenv("TEST_CHECK_CODE") or "2580"
    misses: dict[str, int] = {}

    def test_code(case_id: str, digits: str) -> str:
        if hmac.compare_digest(digits, normal_code):
            outcome, reply = "right code -> asking 'did you send it?'", ASK
        elif misses.get(case_id, 0) == 0:
            misses[case_id] = 1
            outcome, reply = "wrong -> asking once more", RETRY
        else:
            outcome, reply = "wrong again -> not confirmed", RECORDED
        print(f"case {case_id or '-'}: {len(digits)} digits, {outcome}, replied {reply!r}", flush=True)
        return reply

    def test_answer(case_id: str, answer: str) -> str:
        print(f"case {case_id or '-'}: sent the message? {answer or 'unclear'}", flush=True)
        return RECORDED

    print(f"Code webhook on http://localhost:{CODE_WEBHOOK_PORT}/tools/... (Ctrl+C to stop)", flush=True)
    asyncio.run(serve(test_code, on_answer=test_answer))
