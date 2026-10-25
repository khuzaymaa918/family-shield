"""Verifier agent. Owner: Lead (P1). Uses Teammate A and B's functions.

On ReachStudent: call the student with Cartesia. The call agent asks for the check code on the keypad
and sends the digits to the code webhook (services/code_webhook.py), which this agent runs.
The webhook calls on_code(case_id, digits); we classify the code and tell the Guardian with CodeResult.

Normal and danger codes get the SAME spoken reply, so anyone next to the student can't tell them apart.

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
from services.code_webhook import RECORDED, RETRY, start_in_background
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

# case_id -> {"student": name, "guardian": address to report to, "misses": wrong attempts so far}
cases: dict[str, dict] = {}
# The startup context, so the webhook callback (which has no ctx of its own) can message the Guardian.
_ctx: Context | None = None


def _now() -> str:
    return datetime.now().strftime("%I:%M %p")


async def _report(case_id: str, result: str) -> None:
    case = cases.get(case_id)
    if not case or _ctx is None:
        return
    await _ctx.send(case["guardian"], CodeResult(case_id=case_id, result=result, time=_now()))
    _ctx.logger.info(f"Case {case_id}: reported {result}")


async def on_code(case_id: str, digits: str) -> str:
    """Called by the code webhook while the student is on the call. Must return fast."""
    case = cases.get(case_id)
    if not case:
        # Unknown case: still give the normal reply so nothing is revealed on the call.
        return RECORDED
    result = classify_code(case["student"], digits)
    if result in ("normal", "danger"):
        # Same spoken reply for both; the difference only reaches the Guardian.
        asyncio.create_task(_report(case_id, result))
        return RECORDED
    if case["misses"] == 0:
        case["misses"] = 1
        return RETRY
    asyncio.create_task(_report(case_id, "wrong"))
    return RECORDED


@agent.on_event("startup")
async def start_code_webhook(ctx: Context):
    global _ctx
    _ctx = ctx
    start_in_background(on_code)
    warm_moss()  # load the Moss family directory in the background
    ctx.logger.info("Code webhook started on port 8090")


@agent.on_message(model=ReachStudent, replies=Reached)
async def reach_student(ctx: Context, sender: str, msg: ReachStudent):
    cases[msg.case_id] = {"student": msg.student_name, "guardian": sender, "misses": 0}
    # Blocking HTTP, so run it off the event loop.
    delivered = await asyncio.to_thread(deliver_voice_message, msg.phone, case_id=msg.case_id)
    await ctx.send(sender, Reached(case_id=msg.case_id, delivered=delivered))


if __name__ == "__main__":
    agent.run()
