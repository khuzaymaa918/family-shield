"""Cartesia functions. Owner: Teammate A (P2).

Plain Python only: no agents here. The agents call these functions:
    transcribe              voice note -> text (Cartesia speech-to-text), used by the Voice Inspector
    deliver_voice_message   places the verification call (Cartesia agent), used by the Verifier
    make_voice_message      the greeting as an mp3, for trying voices without placing a call
What Cartesia does for us and its known limitations: services/CARTESIA.md.
"""
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
# Any voice from https://play.cartesia.ai/voices. The default (Whitney) is calm and even, for a worried student.
# "or" so a blank CARTESIA_VOICE_ID= line in .env still falls back to the default.
CARTESIA_VOICE_ID = os.getenv("CARTESIA_VOICE_ID") or "f3c7d5d2-c1e1-41a0-bd88-8b5512be5335"

CARTESIA_API = "https://api.cartesia.ai"
CARTESIA_VERSION = "2026-08-14"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

# The student answers the call and types the check code on the keypad; nobody nearby hears the digits.
OUTREACH_SCRIPT = (
    "Hi, this is Family Shield, an AI assistant calling for your family. "
    "They just got a message that says it's from you, and they want to make sure you're okay. "
    "Please enter your four-digit check code on your phone's keypad now."
)


def _headers() -> dict:
    if not CARTESIA_API_KEY:
        raise RuntimeError("Set CARTESIA_API_KEY in .env")
    return {"Authorization": f"Bearer {CARTESIA_API_KEY}", "Cartesia-Version": CARTESIA_VERSION}


def transcribe(audio_file_path: str, language: str = "en") -> str:
    """Turn a voice note into text with Cartesia speech-to-text.

    Accepts mp3, m4a, ogg, wav, webm and more. Pass language="hi" for a Hindi voice note.
    Blocking HTTP: from an async handler, call it as `await asyncio.to_thread(transcribe, path)`.
    """
    with open(audio_file_path, "rb") as audio:
        response = requests.post(
            f"{CARTESIA_API}/stt",
            headers=_headers(),
            files={"file": audio},
            data={"model": "ink-whisper", "language": language},
            timeout=60,
        )
    response.raise_for_status()
    return response.json()["text"]


def make_voice_message(text: str = OUTREACH_SCRIPT, out_path: str = str(SAMPLES_DIR / "outreach.mp3")) -> str:
    """Generate the outreach message as audio with Cartesia text-to-speech.

    Returns the path of the saved mp3 file (samples/outreach.mp3 unless out_path is given).
    """
    response = requests.post(
        f"{CARTESIA_API}/tts/bytes",
        headers=_headers(),
        json={
            "model_id": "sonic-3.6",
            "transcript": text,
            "voice": CARTESIA_VOICE_ID,
            "language": "en",
            "output_format": {"container": "mp3", "sample_rate": 44100, "bit_rate": 128000},
        },
        timeout=60,
    )
    response.raise_for_status()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(response.content)
    return out_path


def deliver_voice_message(phone: str, text: str = OUTREACH_SCRIPT, *, case_id: str) -> bool:
    """Call the student, read `text`, and collect their check code from the keypad.

    The call agent (set up once with `python -m services.cartesia_setup`) greets with `text`, sends the
    digits the student types to the verify_code webhook (services/code_webhook.py) tagged with `case_id`,
    and never reads the digits back. case_id is required so each code reaches the right case.
    `phone` must be a US number in E.164 form, like +14155550123.

    Blocking HTTP: from an async handler, call it as
    `await asyncio.to_thread(deliver_voice_message, phone, case_id=case_id)`.

    Returns True if Cartesia accepted the call (not that someone answered), False if the call couldn't be
    placed. Raises only for setup mistakes: a missing API key or IDs in .env, or an empty case_id.
    """
    if not case_id:
        raise ValueError("deliver_voice_message needs a case_id")
    agent_id = os.getenv("CARTESIA_AGENT_ID")
    from_number_id = os.getenv("CARTESIA_FROM_NUMBER_ID")
    missing = [name for name, value in (("CARTESIA_AGENT_ID", agent_id), ("CARTESIA_FROM_NUMBER_ID", from_number_id)) if not value]
    if missing:
        raise RuntimeError(f"Set {', '.join(missing)} in .env (run python -m services.cartesia_setup to get them)")
    try:
        response = requests.post(
            f"{CARTESIA_API}/agents/calls",
            headers=_headers(),
            json={
                "agent_id": agent_id,
                "from_number_id": from_number_id,
                "ringing_timeout_seconds": 30,
                "outbound_calls": [{"to_number": phone, "dynamic_variables": {"message": text, "case_id": case_id}}],
            },
            timeout=15,
        )
        if not response.ok:
            # Cartesia explains 4xx errors in the body.
            print(f"Cartesia call failed ({response.status_code}): {response.text[:300]}")
            return False
        # One entry per destination, in order. Each has either agent_call_id or error.
        entry = response.json()["calls"][0]
    except (requests.RequestException, ValueError, KeyError, IndexError) as error:
        print(f"Cartesia call failed: {type(error).__name__}")
        return False
    if "error" in entry:
        print(f"Cartesia rejected the call to {phone}: {entry['error']}")
    return "agent_call_id" in entry


if __name__ == "__main__":
    import sys

    # python -m services.cartesia_tools                  -> transcribe + make_voice_message
    # python -m services.cartesia_tools +14155550123     -> also places a real call to that number
    note = SAMPLES_DIR / "note-1.mp3"
    if note.exists():
        print(transcribe(str(note)))
    print(make_voice_message())
    if len(sys.argv) > 1:
        print(deliver_voice_message(sys.argv[1], case_id="manual-test"))
