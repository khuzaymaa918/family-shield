"""Voice Analyst agent. Owner: Lead (P1). Uses Teammate A and B's functions.

On Analyze(note_id): download the note, transcribe it, extract the claims.

Run from the repo root:  python -m agents.voice_analyst.agent
"""
import os

from dotenv import load_dotenv
from uagents import Agent, Context

from services.cartesia_tools import transcribe
from services.data_tools import get_voice_note
from shared.messages import Analyze, Claims

load_dotenv()

agent = Agent(
    name="family_shield_voice_analyst",
    seed=os.getenv("VOICE_ANALYST_SEED", "family-shield-voice-analyst-change-me"),
    port=8001,
    mailbox=True,
)


@agent.on_message(model=Analyze, replies=Claims)
async def analyze(ctx: Context, sender: str, msg: Analyze):
    path = get_voice_note(msg.note_id)
    transcript = transcribe(path)
    # TODO (Lead): ask Claude to extract these fields as JSON from the transcript
    await ctx.send(
        sender,
        Claims(
            case_id=msg.case_id,
            claimed_identity="unknown",
            amount="unknown",
            story="unknown",
            transcript=transcript,
        ),
    )


if __name__ == "__main__":
    agent.run()
