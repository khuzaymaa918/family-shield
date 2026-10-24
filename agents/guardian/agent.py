"""Guardian agent. Owner: Lead (P1).

Talks to parents and students in ASI:One (Chat Protocol) and coordinates
the Voice Analyst, Family agent and Verifier.

Starter version: replies to any ASI:One message with the first safety line.
Next steps are marked TODO. Based on the Fetch.ai Cal Hacks hackpack example.

Run from the repo root:  python -m agents.guardian.agent
"""
import os
from datetime import datetime, timezone
from uuid import uuid4

from dotenv import load_dotenv
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

load_dotenv()

agent = Agent(
    name="family_shield_guardian",
    seed=os.getenv("GUARDIAN_SEED", "family-shield-guardian-change-me"),
    port=8000,
    mailbox=True,
)

chat_proto = Protocol(spec=chat_protocol_spec)

# Case states. Hard rule: only a CodeResult(ok=True) may set CONFIRMED.
PENDING, WAITING_FOR_STUDENT, CONFIRMED, NOT_CONFIRMED = (
    "PENDING", "WAITING_FOR_STUDENT", "CONFIRMED", "NOT_CONFIRMED"
)


def text_reply(text: str, end_session: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(), content=content)


@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id),
    )
    for item in msg.content:
        if isinstance(item, StartSessionContent):
            ctx.logger.info(f"Session started with {sender}")
        elif isinstance(item, TextContent):
            ctx.logger.info(f"Message from {sender}: {item.text}")
            # TODO (Lead): use Claude to turn item.text into a case
            # TODO (Lead): send Analyze -> Voice Analyst, GetFamily -> Family, ReachStudent -> Verifier
            # TODO (Lead): if the sender is a student typing a code, send CheckCode -> Verifier
            await ctx.send(
                sender,
                text_reply("Don't send any money yet. I'm checking with your child now."),
            )


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"Ack from {sender} for {msg.acknowledged_msg_id}")


agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
