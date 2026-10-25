"""Verifier agent. Owner: Lead (P1). Uses Teammate A and B's functions.

On ReachStudent: call the student with Cartesia. On the call:
  1. the student enters their check code on the keypad -> on_code(case_id, digits)
  2. only if the code is right, the call asks "Did you send your family a message asking for money?"
     and the student presses 1 (yes) or 2 (no)              -> on_answer(case_id, "yes" | "no" | "")
Both arrive through the code webhook (services/code_webhook.py), which this agent runs.
The code comes FIRST, so whoever picks up the phone can't just press 1 or 2.

We tell the Guardian one CodeResult per case: "sent", "not_sent", "wrong" or "no_answer".

Before running (once per tunnel URL):
  1. cloudflared tunnel --url http://localhost:8090      (keep it open; copy the https URL)
  2. put that URL in .env as CODE_WEBHOOK_URL, and set CODE_WEBHOOK_SECRET to a long random string
  3. python -m services.cartesia_setup                     (rerun whenever the tunnel URL changes)

Run from the repo root:  python -m agents.verifier.agent
"""
import asyncio
import os
from datetime import datetime

from dotenv import load_dotenv
from uagents import Agent, Context

from services.cartesia_tools import deliver_voice_message
from services.code_webhook import ASK, RECORDED, RETRY, start_in_background
from services.data_tools import classify_code, warm_moss
from shared.messages import CodeResult, Reached, ReachStudent

load_dotenv()

seed = os.getenv("VERIFIER_SEED")
if not seed:
    raise SystemExit("Set VERIFIER_SEED in your .env file first")

agent = Agent(
    name="family_shield_verifier",
    seed=seed,
    port=8003,
    mailbox=True,
)

# case_id -> {"student", "guardian" (address to report to), "misses" (wrong codes so far),
#             "code_ok" (right code entered), "reported" (CodeResult already sent)}
cases: dict[str, dict] = {}
# After a right code, how long to wait for the 1/2 answer before reporting "no_answer".
ANSWER_TIMEOUT_SECONDS = 45
# The startup context, so the webhook callback (which has no ctx of its own) can message the Guardian.
_ctx: Context | None = None


def _now() -> str:
    return datetime.now().strftime("%I:%M %p")


async def _report(case_id: str, result: str) -> None:
    case = cases.get(case_id)
    if not case or _ctx is None or case["reported"]:
        return
    case["reported"] = True  # exactly one result per case
    await _ctx.send(case["guardian"], CodeResult(case_id=case_id, result=result, time=_now()))
    _ctx.logger.info(f"Case {case_id}: reported {result}")


async def _answer_timeout(case_id: str) -> None:
    await asyncio.sleep(ANSWER_TIMEOUT_SECONDS)
    await _report(case_id, "no_answer")  # does nothing if they already answered


async def on_code(case_id: str, digits: str) -> str:
    """Called by the code webhook while the student is on the call. Must return fast."""
    case = cases.get(case_id)
    if not case or case["reported"]:
        return RECORDED
    if case["code_ok"]:
        return ASK  # code already accepted: just ask the question again
    if classify_code(case["student"], digits) == "normal":
        case["code_ok"] = True
        asyncio.create_task(_answer_timeout(case_id))
        return ASK
    if case["misses"] == 0:
        case["misses"] = 1
        return RETRY
    asyncio.create_task(_report(case_id, "wrong"))
    return RECORDED


async def on_answer(case_id: str, answer: str) -> str:
    """The student's 1/2 answer. Only counts after a right code."""
    case = cases.get(case_id)
    if case and case["code_ok"]:
        result = {"yes": "sent", "no": "not_sent"}.get(answer, "no_answer")
        asyncio.create_task(_report(case_id, result))
    return RECORDED


@agent.on_event("startup")
async def start_code_webhook(ctx: Context):
    global _ctx
    _ctx = ctx
    start_in_background(on_code, on_answer)
    warm_moss()  # load the Moss family directory in the background
    ctx.logger.info("Code webhook started on port 8090")


@agent.on_message(model=ReachStudent, replies=Reached)
async def reach_student(ctx: Context, sender: str, msg: ReachStudent):
    cases[msg.case_id] = {"student": msg.student_name, "guardian": sender, "misses": 0,
                          "code_ok": False, "reported": False}
    # Blocking HTTP, so run it off the event loop.
    delivered = await asyncio.to_thread(deliver_voice_message, msg.phone, case_id=msg.case_id)
    await ctx.send(sender, Reached(case_id=msg.case_id, delivered=delivered))


if __name__ == "__main__":
    agent.run()
