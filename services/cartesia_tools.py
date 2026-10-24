"""Cartesia functions. Owner: Teammate A (P2).

Plain Python only: no agents here. The lead's agents call these functions.
Each function currently returns FAKE data so the agents can run today.
Replace the body of each function, keep the name, inputs and output type.
Done by 4 PM.
"""
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
# Any voice from https://play.cartesia.ai/voices. The default (Skylar) is the example voice in Cartesia's docs.
# "or" so a blank CARTESIA_VOICE_ID= line in .env still falls back to the default.
CARTESIA_VOICE_ID = os.getenv("CARTESIA_VOICE_ID") or "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"

CARTESIA_API = "https://api.cartesia.ai"
CARTESIA_VERSION = "2026-08-14"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

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
