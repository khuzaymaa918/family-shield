"""Voice Analyst agent. Owner: Lead (P1). Uses Teammate A and B's functions.

On Analyze(note_id): download the note, transcribe it, extract the claims.

Run from the repo root:  python -m agents.voice_analyst.agent
"""
import asyncio
import os

from dotenv import load_dotenv
from uagents import Agent, Context

from services.cartesia_tools import transcribe
from services.claude_tools import read_transcript
from services.data_tools import get_voice_note
from shared.messages import Analyze, Claims

load_dotenv()

seed = os.getenv("VOICE_ANALYST_SEED")
if not seed:
    raise SystemExit("Set VOICE_ANALYST_SEED in your .env file first")

agent = Agent(
    name="family_shield_voice_analyst",
    seed=seed,
    port=8001,
    mailbox=True,
)


@agent.on_message(model=Analyze, replies=Claims)
async def analyze(ctx: Context, sender: str, msg: Analyze):
    # Both are blocking HTTP calls, so run them off the event loop.
    path = await asyncio.to_thread(get_voice_note, msg.note_id)
    transcript = await asyncio.to_thread(transcribe, path)
    claims = await asyncio.to_thread(read_transcript, transcript)
    story = claims["story"]
    if claims["red_flags"]:
        story += " (warning signs: " + "; ".join(claims["red_flags"]) + ")"
    await ctx.send(
        sender,
        Claims(
            case_id=msg.case_id,
            claimed_identity=claims["claimed_identity"],
            amount=claims["amount"],
            story=story,
            transcript=transcript,
        ),
    )


if __name__ == "__main__":
    agent.run()
