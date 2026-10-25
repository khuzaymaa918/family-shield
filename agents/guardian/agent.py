"""Guardian agent. Owner: Lead (P1).

Talks to the parent in ASI:One (Chat Protocol) and coordinates the other agents:
  parent message -> Claude reads it -> Analyze (Voice Analyst) + GetFamily (Family)
  Contact -> ReachStudent (Verifier) -> the student gets a call, types their check code,
             then answers "Did you send that message?" (1 yes / 2 no)
  CodeResult -> one reply to the parent:
     🟢 REQUEST CONFIRMED  the student entered their code and said they DID send it
     🔴 SCAM               the student entered their code and said they did NOT send it
     🟡 NOT CONFIRMED      wrong code, no answer, no saved number, or no reply in time

HARD RULE: only the student's own answer, given AFTER their check code, can turn a case green or red.
Nothing else (Claude, the transcript, how real the voice sounds, the parent, a timeout) ever decides it.
We never tell the parent to send money, only whether the request really came from their child.

Needs in .env: GUARDIAN_SEED, VOICE_ANALYST_ADDRESS, FAMILY_ADDRESS, VERIFIER_ADDRESS
(each agent prints its address when it starts). ANTHROPIC_API_KEY is optional.

Run from the repo root:  python -m agents.guardian.agent
"""
import asyncio
import json
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
    MetadataContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

from services.claude_tools import read_parent_message
from shared.cards import progress_card, result_card
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
SCAM = "SCAM"
DONE = (CONFIRMED, NOT_CONFIRMED, SCAM)

# case_id -> {"parent", "student", "state", "started", "flags"}
cases: dict[str, dict] = {}
# parent address -> their open case_id
open_case: dict[str, str] = {}
# parents we just asked "what is your child's name?"
asked_name: set[str] = set()
# parent address -> final result text of their last case.
# ASI:One only shows one agent reply per parent message, so later updates can be hidden.
# When the parent asks again ("status"), we reply with this.
last_result: dict[str, tuple] = {}  # (text, card)
STATUS_WORDS = re.compile(
    r"\b(status|update|result|news|any word|what happened|safe|ok|okay|did (he|she|they)|is (he|she|they))\b|\?$",
    re.I)
STATUS_HINT = "\n\nType \"status\" anytime and I'll show you the latest update here."

# ASI:One shows only the LAST agent message that arrives shortly after the parent's message,
# and drops anything later. So we send ONE reply per parent message: we hold it for up to
# REPLY_WAIT_SECONDS, keep improving it as updates come in, and send it early if the case finishes.
REPLY_WAIT_SECONDS = float(os.getenv("REPLY_WAIT_SECONDS", "25"))
# parent address -> {"text": reply waiting to be sent, "card": optional card, "deadline": when to send it anyway}
pending: dict[str, dict] = {}

# ---------- Loop guard ----------
# In some ASI:One chats the user's personal AI sits in the middle and answers our replies with its own
# long messages. Without a guard the two AIs talk forever, burn credits, and could open cases (and
# phone calls) from AI chatter. Real parents send short messages, a few at a time.
LOOP_WINDOW_SECONDS = 60        # look at messages from one sender in this window...
LOOP_MAX_MESSAGES = 5           # ...more than this many = a loop: mute the sender
MUTE_SECONDS = 300
NEW_CASE_COOLDOWN_SECONDS = 90  # one new case per sender per this many seconds
MAX_PARENT_WORDS = 120          # longer than this = almost certainly an AI essay, not a worried parent
AI_CHATTER = re.compile(
    r"\b(i'?m|i am) (\w+, )?(an? )?(ai|assistant|shopping assistant|language model)\b|\bas an ai\b|"
    r"\ban ai assistant\b|i don'?t have the ability|wires crossed|this conversation is empty",
    re.I)
MENTION = re.compile(r"@agent1[0-9a-z]+\s*", re.I)
recent_messages: dict[str, list[float]] = {}
muted_until: dict[str, float] = {}
last_case_at: dict[str, float] = {}


def loop_guard(sender: str, text: str) -> str:
    """Returns why to ignore this message, or "" to handle it."""
    now = time.time()
    if muted_until.get(sender, 0) > now:
        return "muted"
    times = [t for t in recent_messages.get(sender, []) if now - t < LOOP_WINDOW_SECONDS] + [now]
    recent_messages[sender] = times
    if len(times) > LOOP_MAX_MESSAGES:
        muted_until[sender] = now + MUTE_SECONDS
        return "loop"
    if len(text.split()) > MAX_PARENT_WORDS:
        return "too long"
    if AI_CHATTER.search(text):
        return "another AI talking"
    return ""


def card_click(text: str) -> str:
    """A tapped card button arrives as JSON like {"action": "status"}: turn it into the word "status"."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return text
    if isinstance(data, dict) and str(data.get("action", "")).lower() == "status":
        return "status"
    return text


# ASI:One interactive cards (shared/cards.py): a coloured card under our text. Our text always works on its
# own, so if cards don't render, nothing is lost. Turn them off with USE_CARDS=false in .env.
USE_CARDS = os.getenv("USE_CARDS", "true").lower() not in ("false", "0", "no")
RESULT_CARD = {CONFIRMED: "it_was_him", SCAM: "scam", NOT_CONFIRMED: "not_confirmed"}


def text_reply(text: str, card: list | None = None, end_session: bool = False) -> ChatMessage:
    content = [TextContent(type="text", text=text)]
    if card and USE_CARDS:
        content += [block for block in card if isinstance(block, MetadataContent)]
    if end_session:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(), content=content)


def reply_later(parent: str, text: str, card: list | None = None):
    """Queue (or improve) the one reply for the parent's latest message."""
    if parent in pending:
        pending[parent].update(text=text, card=card)
    else:
        pending[parent] = {"text": text, "card": card, "deadline": time.time() + REPLY_WAIT_SECONDS}


async def reply_now(ctx: Context, parent: str, text: str, card: list | None = None):
    """Send right away and drop anything queued (it's out of date now)."""
    pending.pop(parent, None)
    await ctx.send(parent, text_reply(text, card))


async def tell_parent(ctx: Context, case_id: str, text: str, card: list | None = None):
    """An in-progress update: improves the queued reply instead of sending a new message."""
    case = cases.get(case_id)
    if case:
        reply_later(case["parent"], text, card)


async def finish(ctx: Context, case_id: str, state: str, text: str, when: str = ""):
    """Close the case, remember the result for "status", and send it now (with its coloured card)."""
    case = cases[case_id]
    card = result_card(RESULT_CARD[state], case["student"].title(), when or datetime.now().strftime("%I:%M %p"))
    close(case_id, state, text, card)
    await reply_now(ctx, case["parent"], text, card)


@agent.on_interval(period=1.0)
async def flush_replies(ctx: Context):
    now = time.time()
    for parent, item in list(pending.items()):
        if now >= item["deadline"]:
            await reply_now(ctx, parent, item["text"], item.get("card"))


def close(case_id: str, state: str, text: str = "", card: list | None = None):
    case = cases[case_id]
    case["state"] = state
    if text:
        last_result[case["parent"]] = (text, card)
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
    text = card_click(MENTION.sub("", text).strip())
    why = loop_guard(sender, text)
    if why:
        ctx.logger.info(f"Ignoring message from {sender[:16]}... ({why})")
        if why == "loop":
            await reply_now(ctx, sender, (
                "I'm pausing this chat for a few minutes: it looks like another AI assistant is replying "
                "for you. Please open a direct chat with Family Shield (Agentverse -> family_shield_guardian "
                "-> Chat with Agent) and tell me what happened in one short message."))
        return

    # A case is already running for this parent: give a status update.
    if sender in open_case:
        case = cases[open_case[sender]]
        status = (f"Still checking with {case['student'].title()}. Please don't send any money yet."
                  if case["state"] == PENDING else
                  f"I've called {case['student'].title()} and I'm waiting for them to enter your family "
                  "check code and tell me whether they sent that message. Please don't send any money yet.")
        if case.get("claims"):
            status += "\n\n" + case["claims"]
        if case.get("scam"):
            status += "\n\n" + case["scam"]
        card = progress_card(case["student"].title()) if case["state"] == WAITING_FOR_STUDENT else None
        reply_later(sender, status + STATUS_HINT, card)  # if the result lands in the next few seconds, it replaces this
        return

    # The case is finished: repeat the result (ASI:One may have hidden it).
    if sender in last_result and len(text.split()) <= 6 and STATUS_WORDS.search(text.strip()):
        await reply_now(ctx, sender, *last_result[sender])
        return

    # Just finished a case a moment ago: don't open another one from a follow-up.
    if sender in last_result and time.time() - last_case_at.get(sender, 0) < NEW_CASE_COOLDOWN_SECONDS:
        await reply_now(ctx, sender, *last_result[sender])
        return

    info = await asyncio.to_thread(read_parent_message, text)
    if sender in asked_name and not info["student_name"] and len(text.split()) <= 3:
        # They are answering our "what is your child's name?" question.
        info["student_name"] = text.strip().split()[0].strip(".,!")
        info["is_new_case"] = True
    if sender in asked_name and info["student_name"]:
        info["is_new_case"] = True
    if not info["is_new_case"]:
        await reply_now(ctx, sender, (
            "Hi, I'm Family Shield. If you got a call, voice note or text that claims to be your child "
            "and asks for money, tell me your child's name (and the voice note id if you have one). "
            "I'll check with them directly before you do anything."))
        return
    if not info["student_name"]:
        asked_name.add(sender)
        await reply_now(ctx, sender, (
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
    last_case_at[sender] = time.time()
    ctx.logger.info(f"Case {case_id} opened for {info['student_name']}")

    last_result.pop(sender, None)
    cases[case_id]["warning"] = ("Warning signs I see: " + "; ".join(info["red_flags"]) + ".") if info["red_flags"] else ""
    reply = f"Don't send any money yet. I'm checking with {info['student_name'].title()} directly now."
    if cases[case_id]["warning"]:
        reply += "\n\n" + cases[case_id]["warning"]
    reply += STATUS_HINT
    reply_later(sender, reply)  # held a few seconds so the "calling now" update can replace it

    if VOICE_ANALYST:
        # An exact note id if the parent gave one, otherwise the newest note named after the child.
        note = info["note_id"] or info["student_name"].lower()
        await ctx.send(VOICE_ANALYST, Analyze(case_id=case_id, note_id=note))
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
        text = (f"Don't send any money yet. I'm calling {case['student'].title()} now. They'll enter your "
                "family check code and tell me whether they really sent that message.")
        if case.get("warning"):
            text += "\n\n" + case["warning"]
        await tell_parent(ctx, msg.case_id, text + STATUS_HINT, progress_card(case["student"].title()))
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
    # Only here can a case turn green or red: the student's own answer after their check code.
    if msg.result == "sent":
        await finish(ctx, msg.case_id, CONFIRMED,
            f"🟢 REQUEST CONFIRMED. {name} entered your family check code and confirmed at {msg.time} that "
            f"they DID send that message. The request really came from {name}. "
            f"Talk to {name} directly about it before you send anything.", when=msg.time)
    elif msg.result == "not_sent":
        await finish(ctx, msg.case_id, SCAM,
            f"🔴 SCAM. {name} entered your family check code and confirmed at {msg.time} that they did NOT "
            f"send that message. Someone is pretending to be {name}, possibly with a cloned voice. "
            "Do not send any money and do not reply to whoever contacted you.", when=msg.time)
    elif msg.result == "no_answer":
        await finish(ctx, msg.case_id, NOT_CONFIRMED,
            f"🟡 NOT CONFIRMED. {name} entered your family check code but didn't say whether they sent "
            f"that message. Don't send money until you talk to {name} directly.", when=msg.time)
    else:
        await finish(ctx, msg.case_id, NOT_CONFIRMED,
            f"🟡 NOT CONFIRMED. The check code entered at {msg.time} was wrong. "
            "Don't send money. Call your child on the number you already know.", when=msg.time)


# ---------- Timeout: no code in time -> amber ----------

@agent.on_interval(period=15.0)
async def check_timeouts(ctx: Context):
    now = time.time()
    for case_id, case in list(cases.items()):
        if case["state"] == WAITING_FOR_STUDENT and now - case["started"] > CODE_TIMEOUT_SECONDS:
            await finish(ctx, case_id, NOT_CONFIRMED,
                f"🟡 NOT CONFIRMED. {case['student'].title()} hasn't entered the check code yet. "
                "They may just be busy. "
                "Don't send money until you reach them yourself.")


agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
