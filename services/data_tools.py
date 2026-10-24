"""Storage, Moss and code-check functions. Owner: Teammate B (P3).

Plain Python only: no agents here. The lead's agents call these functions.
Each function currently uses FAKE data so the agents can run today.
Replace the body of each function, keep the name, inputs and output type.
Done by 4 PM.
"""
import hashlib
import os

from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MOSS_API_KEY = os.getenv("MOSS_API_KEY")


def hash_code(code: str) -> str:
    """Store this, never the plain code."""
    return hashlib.sha256(code.strip().encode()).hexdigest()


# FAKE in-memory store until Moss is set up
_FAKE_CONTACTS = {
    "arjun": {"name": "Arjun", "phone": "+10000000000", "code_hash": hash_code("2580")},
}


def get_voice_note(note_id: str) -> str:
    """Download a voice note from Supabase storage (bucket 'voice-notes').

    Returns the local file path.
    """
    # TODO (Teammate B): download from Supabase storage
    return f"samples/{note_id}.mp3"


def save_contact(name: str, phone: str, code: str) -> None:
    """Save a student's phone and hashed check code in Moss."""
    # TODO (Teammate B): store in Moss instead of the fake dict
    _FAKE_CONTACTS[name.lower()] = {"name": name, "phone": phone, "code_hash": hash_code(code)}


def get_contact(name: str) -> dict:
    """Look up a student's contact in Moss. Returns {} if not found."""
    # TODO (Teammate B): read from Moss
    contact = _FAKE_CONTACTS.get(name.lower(), {})
    return {"name": contact.get("name"), "phone": contact.get("phone")} if contact else {}


def check_code(name: str, code: str) -> bool:
    """True only if the code matches the stored hash for this student."""
    # TODO (Teammate B): read the stored hash from Moss
    contact = _FAKE_CONTACTS.get(name.lower())
    return bool(contact) and contact["code_hash"] == hash_code(code)


if __name__ == "__main__":
    print(get_voice_note("note-1"))
    print(get_contact("Arjun"))
    print("right code:", check_code("Arjun", "2580"))
    print("wrong code:", check_code("Arjun", "1111"))
