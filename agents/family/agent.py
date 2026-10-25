"""Family agent. Owner: Lead (P1). Uses Teammate B's functions.

On GetFamily(student_name): return the student's verified phone from Moss.
The check code never leaves this agent or the Verifier.

Run from the repo root:  python -m agents.family.agent
"""
import asyncio
import os

from dotenv import load_dotenv
from uagents import Agent, Context

from services.data_tools import get_contact, warm_moss
from shared.messages import Contact, GetFamily
from shared.trust import guardian_address, trusted

load_dotenv()
GUARDIAN = guardian_address()

seed = os.getenv("FAMILY_SEED")
if not seed:
    raise SystemExit("Set FAMILY_SEED in your .env file first")

agent = Agent(
    name="family_shield_family",
    seed=seed,
    port=8002,
    mailbox=True,
)


@agent.on_event("startup")
async def load_directory(ctx: Context):
    warm_moss()  # load the Moss family directory in the background


@agent.on_message(model=GetFamily, replies=Contact)
async def get_family(ctx: Context, sender: str, msg: GetFamily):
    # Only the Guardian may look up a student's phone number.
    if not trusted(sender, GUARDIAN):
        ctx.logger.warning(f"Ignoring GetFamily from {sender} (not the Guardian)")
        return
    contact = await asyncio.to_thread(get_contact, msg.student_name)
    await ctx.send(
        sender,
        Contact(case_id=msg.case_id, student_name=msg.student_name, phone=contact.get("phone") or ""),
    )


if __name__ == "__main__":
    agent.run()
