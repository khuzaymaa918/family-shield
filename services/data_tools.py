"""Storage, Moss and code-check functions. Owner: Teammate B (P3).

Plain Python only: no agents here. The lead's agents call these functions.
Each function currently uses FAKE data so the agents can run today.
Replace the body of each function, keep the name, inputs and output type.
Done by 4 PM.
"""
import hashlib
import hmac
import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MOSS_API_KEY = os.getenv("MOSS_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

def hash_code(code: str) -> str:
    """Store this, never the plain code."""
    return hashlib.sha256(code.strip().encode()).hexdigest()


# FAKE in-memory store until Moss is set up
# Demo family: normal code 2580, danger code 7193 (same defaults as services/code_webhook.py's test mode).
# Put a teammate's real US phone number here (E.164, like +14155550123) for the demo call.
_FAKE_CONTACTS = {
    "arjun": {
        "name": "Arjun",
        "phone": os.getenv("DEMO_STUDENT_PHONE") or "+10000000000",
        "code_hash": hash_code("2580"),
        "danger_hash": hash_code("7193"),
    },
}


def get_voice_note(note_id: str) -> str:
    local_path = f"samples/{note_id}.mp3"
    os.makedirs("samples", exist_ok=True)

    if supabase:
        try:
            # Supabase 'voice-notes' 버킷에서 실제 음성 파일 다운로드
            data = supabase.storage.from_("voice-notes").download(f"{note_id}.mp3")
            with open(local_path, "wb") as f:
                f.write(data)
            return local_path
        except Exception as e:
            print(f"[Supabase Storage Note] {e}. Falling back to default path.")

    return local_path



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


def classify_code(name: str, code: str) -> str:
    """Returns "normal", "danger" or "wrong" for the digits a student entered.

    Compares hashes in constant time so timing doesn't leak which code was close.
    """
    # TODO (Teammate B): read both stored hashes from Moss
    contact = _FAKE_CONTACTS.get(name.lower())
    if not contact:
        return "wrong"
    entered = hash_code(code)
    if hmac.compare_digest(entered, contact["code_hash"]):
        return "normal"
    if contact.get("danger_hash") and hmac.compare_digest(entered, contact["danger_hash"]):
        return "danger"
    return "wrong"


if __name__ == "__main__":
    print(get_voice_note("note-1"))
    print(get_contact("Arjun"))
    print("right code:", check_code("Arjun", "2580"))
    print("wrong code:", check_code("Arjun", "1111"))
