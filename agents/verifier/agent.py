"""Verifier agent. Owner: Lead (P1). Uses Teammate A and B's functions.

On ReachStudent: deliver the Cartesia voice message to the student's phone.
On CheckCode: compare the code with the stored hash, reply CodeResult.

Run from the repo root:  python -m agents.verifier.agent
"""
import os
from datetime import datetime

from dotenv import load_dotenv
from uagents import Agent, Context

from services.cartesia_tools import deliver_voice_message
from services.data_tools import check_code
from shared.messages import CheckCode, CodeResult, Reached, ReachStudent

load_dotenv()

agent = Agent(
    name="family_shield_verifier",
    seed=os.getenv("VERIFIER_SEED", "family-shield-verifier-change-me"),
    port=8003,
    mailbox=True,
)


@agent.on_message(model=ReachStudent, replies=Reached)
async def reach_student(ctx: Context, sender: str, msg: ReachStudent):
    delivered = deliver_voice_message(msg.phone)
    await ctx.send(sender, Reached(case_id=msg.case_id, delivered=delivered))


@agent.on_message(model=CheckCode, replies=CodeResult)
async def verify_code(ctx: Context, sender: str, msg: CheckCode):
    ok = check_code(msg.student_name, msg.code)
    await ctx.send(
        sender,
        CodeResult(case_id=msg.case_id, ok=ok, time=datetime.now().strftime("%I:%M %p")),
    )


if __name__ == "__main__":
    agent.run()
