"""Receives the check code a student types on the keypad during the Family Shield call. Owner: Teammate A (P2).

The Cartesia call agent sends the digits here through its verify_code webhook tool. This module only
receives them; whoever starts it decides what a code means (check_code, CodeResult to the Guardian).

Inside the Verifier agent:

    from services.code_webhook import RECORDED, RETRY, start_in_background

    async def on_code(case_id: str, digits: str) -> str:
        # Three outcomes. Normal and danger codes MUST get the same reply, or a bystander can tell them apart.
        #   normal code -> tell the Guardian "confirmed",      return RECORDED
        #   danger code -> tell the Guardian "danger signal",  return RECORDED
        #   neither     -> return RETRY once, then RECORDED and leave the case unconfirmed
        # Return fast: the call agent waits on this reply. Do slow work (ctx.send to the Guardian) in
        # asyncio.create_task(...). If this raises or takes longer than HANDLER_TIMEOUT_SECS, the student
        # still hears the normal reply and the error is logged.
        ...

    @agent.on_event("startup")
    async def start_code_webhook(ctx):
        start_in_background(on_code)

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
# Cartesia's tool timeout is 10s (cartesia_setup.py). Answer well before it so the agent never improvises.
HANDLER_TIMEOUT_SECS = 5

log = logging.getLogger(__name__)

CodeHandler = Callable[[str, str], str | Awaitable[str]]


class CodeIn(BaseModel):
    # The LLM may send the code as a number; accept it rather than failing the tool call.
    model_config = ConfigDict(coerce_numbers_to_str=True)
    case_id: str | None = ""
    code: str


def _digits(text: str) -> str:
    # Keypad gives 0-9; speech-to-text may give other scripts (e.g. Devanagari), so map every digit to 0-9.
    return "".join(str(unicodedata.digit(ch)) for ch in text if unicodedata.digit(ch, None) is not None)


def make_app(on_code: CodeHandler) -> FastAPI:
    app = FastAPI(title="Family Shield code webhook")

    @app.post("/tools/verify_code")
    async def verify_code(body: CodeIn, authorization: str | None = Header(default=None)) -> dict:
        expected = f"Bearer {CODE_WEBHOOK_SECRET}"
        if not CODE_WEBHOOK_SECRET or not hmac.compare_digest((authorization or "").encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="unauthorized")
        try:
            reply = on_code(body.case_id or "", _digits(body.code))
            if inspect.isawaitable(reply):
                reply = await asyncio.wait_for(reply, HANDLER_TIMEOUT_SECS)
        except Exception as error:
            # Never let a handler failure change what the student hears. Log the type only, never the digits.
            log.error("code handler failed for case %s: %s", body.case_id or "-", type(error).__name__)
            reply = RECORDED
        return {"result": reply if reply in (RECORDED, RETRY) else RECORDED}

    return app


async def serve(on_code: CodeHandler, port: int = CODE_WEBHOOK_PORT) -> None:
    """Runs the webhook server in the current event loop until cancelled."""
    if not CODE_WEBHOOK_SECRET:
        raise RuntimeError("Set CODE_WEBHOOK_SECRET in .env")
    # Loopback only: cloudflared forwards from localhost, so nothing on the venue Wi-Fi can reach it directly.
    config = uvicorn.Config(make_app(on_code), host="127.0.0.1", port=port, log_level="warning")
    try:
        await uvicorn.Server(config).serve()
    except SystemExit as error:
        # uvicorn calls sys.exit when the port is taken; inside a task that would kill the whole agent.
        raise RuntimeError(f"Code webhook could not start on port {port} (already in use?)") from error


_tasks: set[asyncio.Task] = set()


def start_in_background(on_code: CodeHandler, port: int = CODE_WEBHOOK_PORT) -> asyncio.Task:
    """Starts serve() as a task in the running loop. Fails now if the secret is missing; logs later failures."""
    if not CODE_WEBHOOK_SECRET:
        raise RuntimeError("Set CODE_WEBHOOK_SECRET in .env")
    task = asyncio.get_running_loop().create_task(serve(on_code, port))
    _tasks.add(task)

    def _report(done: asyncio.Task) -> None:
        _tasks.discard(done)
        if not done.cancelled() and done.exception():
            log.error("Code webhook stopped: %s", done.exception())

    task.add_done_callback(_report)
    return task


if __name__ == "__main__":
    # Test handler: classifies against TEST_CHECK_CODE (default 2580) and TEST_DANGER_CODE (default 7193)
    # and prints only the outcome, never the digits themselves.
    normal_code = os.getenv("TEST_CHECK_CODE") or "2580"
    danger_code = os.getenv("TEST_DANGER_CODE") or "7193"
    misses: dict[str, int] = {}

    def test_handler(case_id: str, digits: str) -> str:
        if hmac.compare_digest(digits, normal_code):
            outcome, reply = "normal code -> confirmed", RECORDED
        elif hmac.compare_digest(digits, danger_code):
            outcome, reply = "DANGER code -> silent alarm", RECORDED
        elif misses.get(case_id, 0) == 0:
            misses[case_id] = 1
            outcome, reply = "neither -> asking once more", RETRY
        else:
            outcome, reply = "neither again -> not confirmed", RECORDED
        print(f"case {case_id or '-'}: {len(digits)} digits, {outcome}, replied {reply!r}", flush=True)
        return reply

    print(f"Code webhook on http://localhost:{CODE_WEBHOOK_PORT}/tools/verify_code (Ctrl+C to stop)", flush=True)
    asyncio.run(serve(test_handler))
