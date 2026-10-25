"""Scam Intel agent. Owner: Lead (P1).

On CheckScam(text): compare the story with real scam reports (collected with Apify, stored in Moss)
and reply with a one-line pattern check written by Claude. Information only: it never decides
whether the message is real. Only the student's answer on the verification call does.

Seed the reports once:  python -m services.scam_intel seed
Run from the repo root:  python -m agents.scam_intel.agent
"""
import asyncio
import os

from dotenv import load_dotenv
from uagents import Agent, Context

from services.scam_intel import check_story, warm
from shared.messages import CheckScam, ScamReport

load_dotenv()

seed = os.getenv("SCAM_INTEL_SEED")
if not seed:
    raise SystemExit("Set SCAM_INTEL_SEED in your .env file first")

agent = Agent(
    name="family_shield_scam_intel",
    seed=seed,
    port=8004,
    mailbox=True,
)


@agent.on_event("startup")
async def load_reports(ctx: Context):
    warm()  # load the scam-patterns index in the background


@agent.on_message(model=CheckScam, replies=ScamReport)
async def check(ctx: Context, sender: str, msg: CheckScam):
    report = await asyncio.to_thread(check_story, msg.text)
    ctx.logger.info(f"Case {msg.case_id}: {report['matches']} matching scam reports")
    await ctx.send(sender, ScamReport(case_id=msg.case_id, **report))


if __name__ == "__main__":
    agent.run()
