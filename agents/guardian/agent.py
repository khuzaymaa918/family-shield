"""Guardian agent. Owner: Lead (P1).

Talks to the parent in ASI:One (Chat Protocol) and coordinates the other agents:
  parent message -> Claude reads it -> Analyze (Voice Analyst) + GetFamily (Family)
  Contact -> ReachStudent (Verifier) -> the student gets a call and types a code
  CodeResult -> green / amber / danger reply to the parent

HARD RULE: only CodeResult(result="normal") may set CONFIRMED. Nothing else
(Claude, the transcript, the parent, a timeout) can ever say "it's really them".

Needs in .env: GUARDIAN_SEED, VOICE_ANALYST_ADDRESS, FAMILY_ADDRESS, VERIFIER_ADDRESS
(each agent prints its address when it starts). ANTHROPIC_API_KEY is optional.

Run from the repo root:  python -m agents.guardian.agent
"""
import asyncio
import os
import re
import time
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

from services.claude_tools import read_parent_message
from shared.messages import Analyze, Claims, CodeResult, Contact, GetFamily, Reached, ReachStudent

load_dotenv()

seed = os.getenv("GUARDIAN_SEED")
if not seed:
    raise SystemExit("Set GUARDIAN_SEED in your .env file first")

VOICE_ANALYST = os.getenv("VOICE_ANALYST_ADDRESS", "")
FAMILY = os.getenv("FAMILY_ADDRESS", "")
VERIFIER = os.getenv("VERIFIER_ADDRESS", "")
# How long to wait for the student's code before telling the parent "not confirmed".
CODE_TIMEOUT_SECONDS = int(os.getenv("CODE_TIMEOUT_SECONDS", "180"))

agent = Agent(
    name="family_shield_guardian",
    seed=seed,
    port=8000,
    mailbox=True,
)

chat_proto = Protocol(spec=chat_protocol_spec)

PENDING, WAITING_FOR_STUDENT, CONFIRMED, NOT_CONFIRMED = (
    "PENDING", "WAITING_FOR_STUDENT", "CONFIRMED", "NOT_CONFIRMED"
)
DANGER = "DANGER"
DONE = (CONFIRMED, NOT_CONFIRMED, DANGER)

# case_id -> {"parent", "student", "state", "started", "flags"}
cases: dict[str, dict] = {}
# parent address -> their open case_id
open_case: dict[str, str] = {}
# parents we just asked "what is your child's name?"
asked_name: set[str] = set()
# parent address -> final result text of their last case.
# ASI:One only shows one agent reply per parent message, so later updates can be hidden.
# When the parent asks again ("status"), we reply with this.
last_result: dict[str, str] = {}
STATUS_WORDS = re.compile(r"\b(status|update|result|news|any word|did (he|she|they)|is (he|she|they))\b|\?$", re.I)
STATUS_HINT = "\n\nType \"status\" anytime for the latest update."


def text_reply(text: str, end_session: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(), content=content)


async def tell_parent(ctx: Context, case_id: str, text: str, end_session: bool = False):
    case = cases.get(case_id)
    if case:
        await ctx.send(case["parent"], text_reply(text, end_session))


async def finish(ctx: Context, case_id: str, state: str, text: str):
    """Close the case, remember the result for "status", and tell the parent."""
    close(case_id, state, text)
    await tell_parent(ctx, case_id, text)


def close(case_id: str, state: str, text: str = ""):
    case = cases[case_id]
    case["state"] = state
    if text:
        last_result[case["parent"]] = text
    if open_case.get(case["parent"]) == case_id:
        del open_case[case["parent"]]


# ---------- Parent chat (ASI:One) ----------

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
            await handle_parent_text(ctx, sender, item.text)


async def handle_parent_text(ctx: Context, sender: str, text: str):
    # A case is already running for this parent: give a status update.
    if sender in open_case:
        case = cases[open_case[sender]]
        status = (f"Still checking with {case['student'].title()}. Please don't send any money yet."
                  if case["state"] == PENDING else
                  f"I've called {case['student'].title()} and I'm waiting for them to enter your family "
                  "check code. Please don't send any money yet.")
        if case.get("claims"):
            status += "\n\n" + case["claims"]
        await ctx.send(sender, text_reply(status + STATUS_HINT))
        return

    # The case is finished: repeat the result (ASI:One may have hidden it).
    if sender in last_result and len(text.split()) <= 6 and STATUS_WORDS.search(text.strip()):
        await ctx.send(sender, text_reply(last_result[sender]))
        return

    info = await asyncio.to_thread(read_parent_message, text)
    if sender in asked_name and not info["student_name"] and len(text.split()) <= 3:
        # They are answering our "what is your child's name?" question.
        info["student_name"] = text.strip().split()[0].strip(".,!")
        info["is_new_case"] = True
    if sender in asked_name and info["student_name"]:
        info["is_new_case"] = True
    if not info["is_new_case"]:
        await ctx.send(sender, text_reply(
            "Hi, I'm Family Shield. If you got a call, voice note or text that claims to be your child "
            "and asks for money, tell me your child's name (and the voice note id if you have one). "
            "I'll check with them directly before you do anything."))
        return
    if not info["student_name"]:
        asked_name.add(sender)
        await ctx.send(sender, text_reply(
            "Don't send any money yet. What is your child's first name? I'll check with them directly."))
        return

    asked_name.discard(sender)
    case_id = uuid4().hex[:8]
    cases[case_id] = {
        "parent": sender,
        "student": info["student_name"].lower(),
        "state": PENDING,
        "started": time.time(),
        "flags": info["red_flags"],
    }
    open_case[sender] = case_id
    ctx.logger.info(f"Case {case_id} opened for {info['student_name']}")

    last_result.pop(sender, None)
    cases[case_id]["warning"] = ("Warning signs I see: " + "; ".join(info["red_flags"]) + ".") if info["red_flags"] else ""
    reply = f"Don't send any money yet. I'm checking with {info['student_name'].title()} directly now."
    if cases[case_id]["warning"]:
        reply += "\n\n" + cases[case_id]["warning"]
    reply += STATUS_HINT
    await ctx.send(sender, text_reply(reply))

    if info["note_id"] and VOICE_ANALYST:
        await ctx.send(VOICE_ANALYST, Analyze(case_id=case_id, note_id=info["note_id"]))
    if not FAMILY:
        await tell_parent(ctx, case_id, "Setup problem: FAMILY_ADDRESS is not set, so I can't look up your child.")
        return
    await ctx.send(FAMILY, GetFamily(case_id=case_id, student_name=info["student_name"]))


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"Ack from {sender} for {msg.acknowledged_msg_id}")


# ---------- Messages from our own agents ----------

@agent.on_message(model=Claims)
async def on_claims(ctx: Context, sender: str, msg: Claims):
    if msg.case_id not in cases or cases[msg.case_id]["state"] in DONE:
        return
    lines = ["What the voice note claims (this does NOT prove who it is):"]
    if msg.claimed_identity != "unknown":
        lines.append(f"- Says it's: {msg.claimed_identity}")
    if msg.amount != "unknown":
        lines.append(f"- Asks for: {msg.amount}")
    if msg.story != "unknown":
        lines.append(f"- Story: {msg.story}")
    if len(lines) > 1:
        # Stored, not sent: a new message would hide the one already on screen. Shown on "status".
        cases[msg.case_id]["claims"] = "\n".join(lines)


@agent.on_message(model=Contact)
async def on_contact(ctx: Context, sender: str, msg: Contact):
    case = cases.get(msg.case_id)
    if not case or case["state"] in DONE:
        return
    if not msg.phone:
        await finish(ctx, msg.case_id, NOT_CONFIRMED,
            f"🟡 NOT CONFIRMED. I don't have a verified number for {msg.student_name.title()}, "
            "so I can't check. Don't send money. Call your child on the number you already know.")
        return
    if not VERIFIER:
        await tell_parent(ctx, msg.case_id, "Setup problem: VERIFIER_ADDRESS is not set.")
        return
    case["state"] = WAITING_FOR_STUDENT
    case["started"] = time.time()
    await ctx.send(VERIFIER, ReachStudent(case_id=msg.case_id, student_name=msg.student_name, phone=msg.phone))


@agent.on_message(model=Reached)
async def on_reached(ctx: Context, sender: str, msg: Reached):
    case = cases.get(msg.case_id)
    if not case or case["state"] in DONE:
        return
    if msg.delivered:
        text = (f"Don't send any money yet. I'm calling {case['student'].title()} now and asking for "
                "your family check code.")
        if case.get("warning"):
            text += "\n\n" + case["warning"]
        await tell_parent(ctx, msg.case_id, text + STATUS_HINT)
    else:
        await finish(ctx, msg.case_id, NOT_CONFIRMED,
            f"🟡 NOT CONFIRMED. I couldn't reach {case['student'].title()}. "
            "Don't send money. Try calling them on the number you already know.")


@agent.on_message(model=CodeResult)
async def on_code_result(ctx: Context, sender: str, msg: CodeResult):
    case = cases.get(msg.case_id)
    if not case or case["state"] in DONE:
        return
    name = case["student"].title()
    if msg.result == "normal":
        # The ONLY place that may set CONFIRMED.
        await finish(ctx, msg.case_id, CONFIRMED,
            f"🟢 CONFIRMED. {name} entered your family check code at {msg.time}. "
            f"{name} is safe and did not send that message. Do not send money to whoever contacted you.")
    elif msg.result == "danger":
        await finish(ctx, msg.case_id, DANGER,
            f"🔴 DANGER SIGNAL. {name} entered the danger code at {msg.time}. "
            "They may be with someone and unable to talk freely. Do not send money. "
            "Call 911 now and tell them your child may be in danger.")
    else:
        await finish(ctx, msg.case_id, NOT_CONFIRMED,
            f"🟡 NOT CONFIRMED. The code entered at {msg.time} was wrong. "
            "Don't send money. Call your child on the number you already know.")


# ---------- Timeout: no code in time -> amber ----------

@agent.on_interval(period=15.0)
async def check_timeouts(ctx: Context):
    now = time.time()
    for case_id, case in list(cases.items()):
        if case["state"] == WAITING_FOR_STUDENT and now - case["started"] > CODE_TIMEOUT_SECONDS:
            await finish(ctx, case_id, NOT_CONFIRMED,
                f"🟡 NOT CONFIRMED. {case['student'].title()} hasn't entered the check code yet. "
                "That doesn't mean they're in danger, they may just be busy. "
                "Don't send money until you reach them yourself.")


agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
