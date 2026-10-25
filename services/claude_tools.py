"""Claude helpers. Owner: Lead (P1).

Plain Python only. Every function has a simple fallback so the demo still runs
if ANTHROPIC_API_KEY is missing or the call fails.
"""
import json
import os
import re

from dotenv import load_dotenv

load_dotenv()
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

_client = None


def _claude():
    global _client
    if _client is None and os.getenv("ANTHROPIC_API_KEY"):
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def _ask_json(system: str, user: str) -> dict:
    """Ask Claude for a JSON object. Returns {} on any problem."""
    client = _claude()
    if client is None:
        return {}
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=system + "\nReply with ONE JSON object only. No prose, no code fences.",
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        match = re.search(r"\{.*\}", text, re.S)
        return json.loads(match.group(0)) if match else {}
    except Exception as e:  # network, auth, bad JSON: fall back
        print(f"[claude_tools] Claude call failed: {e}")
        return {}


INTAKE_SYSTEM = """You help a parent who got a suspicious message that claims to be from their child
(a possible AI voice-clone money scam). Read the parent's chat message and pull out:
- "student_name": the child's first name, or "" if not given
- "note_id": the voice note id if the parent pasted one (like "arjun-1" or "note-1"), or ""
- "amount": money demanded, or ""
- "red_flags": a list of up to 3 short scam warning signs you see (urgency, secrecy, gift cards, crypto, wire, "don't tell anyone", new number)
- "is_new_case": true if the parent is reporting a suspicious message, false if it's small talk or a question"""


def read_parent_message(text: str) -> dict:
    """Turn the parent's chat text into case details."""
    data = _ask_json(INTAKE_SYSTEM, text)
    note = re.search(r"\b[a-z]+-\d+\b", text, re.I)  # "arjun-1", "note-1"
    name = (data.get("student_name") or "").strip()
    if not name:  # fallback without Claude: "from Arjun", "my son Arjun", ...
        m = re.search(r"\b(?:from|son|daughter|child|kid|named|it's|its)\s+([A-Z][a-z]+)", text)
        name = m.group(1) if m else ""
    return {
        "student_name": name,
        "note_id": (data.get("note_id") or (note.group(0) if note else "")).strip().lower(),
        "amount": str(data.get("amount") or "").strip(),
        "red_flags": [str(f) for f in (data.get("red_flags") or [])][:3],
        "is_new_case": bool(data.get("is_new_case", True)),
    }


CLAIMS_SYSTEM = """You read the transcript of a voice note that claims to be from a family member asking for help.
Pull out:
- "claimed_identity": who the speaker says they are
- "amount": money asked for, or "unknown"
- "story": the story in one short sentence
- "red_flags": up to 3 short scam warning signs"""


def read_transcript(transcript: str) -> dict:
    """Turn a voice-note transcript into claims."""
    data = _ask_json(CLAIMS_SYSTEM, transcript or "(empty transcript)")
    return {
        "claimed_identity": str(data.get("claimed_identity") or "unknown"),
        "amount": str(data.get("amount") or "unknown"),
        "story": str(data.get("story") or "unknown"),
        "red_flags": [str(f) for f in (data.get("red_flags") or [])][:3],
    }


if __name__ == "__main__":
    print(read_parent_message("I got a voice note from Arjun crying, says he needs $2000 in gift cards now. note-1"))
    print(read_transcript("Mom it's me Arjun, I crashed the car, I need two thousand dollars right now, don't tell dad"))
