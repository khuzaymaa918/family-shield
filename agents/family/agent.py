"""Family agent. Owner: Lead (P1). Uses Teammate B's functions.

On GetFamily(student_name): return the student's verified phone from Moss.
The check code never leaves this agent or the Verifier.

Run from the repo root:  python -m agents.family.agent
"""
import os

from dotenv import load_dotenv
from uagents import Agent, Context

from services.data_tools import get_contact
from shared.messages import Contact, GetFamily

load_dotenv()

agent = Agent(
    name="family_shield_family",
    seed=os.getenv("FAMILY_SEED", "family-shield-family-change-me"),
    port=8002,
    mailbox=True,
)


@agent.on_message(model=GetFamily, replies=Contact)
async def get_family(ctx: Context, sender: str, msg: GetFamily):
    contact = get_contact(msg.student_name)
    await ctx.send(
        sender,
        Contact(case_id=msg.case_id, student_name=msg.student_name, phone=contact.get("phone") or ""),
    )


if __name__ == "__main__":
    agent.run()
