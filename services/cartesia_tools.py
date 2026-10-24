"""Cartesia functions. Owner: Teammate A (P2).

Plain Python only: no agents here. The lead's agents call these functions.
Each function currently returns FAKE data so the agents can run today.
Replace the body of each function, keep the name, inputs and output type.
Done by 4 PM.
"""
import os

import requests
from dotenv import load_dotenv

load_dotenv()
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")

CARTESIA_API = "https://api.cartesia.ai"
CARTESIA_VERSION = "2026-08-14"

OUTREACH_SCRIPT = (
    "Hi, this is Family Shield, an AI assistant calling for your mom. "
    "Someone sent her a message claiming to be you. "
    "Please open Family Shield in ASI:One and enter your check code."
)


def _headers() -> dict:
    return {"Authorization": f"Bearer {CARTESIA_API_KEY}", "Cartesia-Version": CARTESIA_VERSION}


def transcribe(audio_file_path: str, language: str = "en") -> str:
    """Turn a voice note into text with Cartesia speech-to-text.

    Accepts mp3, m4a, ogg, wav, webm and more. Pass language="hi" for a Hindi voice note.
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


def make_voice_message(text: str = OUTREACH_SCRIPT) -> str:
    """Generate the outreach message as audio with Cartesia text-to-speech.

    Returns the path of the saved audio file.
    """
    # TODO (Teammate A): call Cartesia text-to-speech and save the audio
    return "samples/outreach_fake.mp3"


def deliver_voice_message(phone: str, text: str = OUTREACH_SCRIPT) -> bool:
    """Deliver the outreach message to a phone (outbound call that plays it).

    Returns True if the call/message went out.
    """
    # TODO (Teammate A): find in Cartesia's docs how to place the outbound call
    print(f"[FAKE] Would deliver voice message to {phone}")
    return True


if __name__ == "__main__":
    print(transcribe("samples/note-1.mp3"))
    print(make_voice_message())
    print(deliver_voice_message("+10000000000"))
