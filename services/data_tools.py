"""Storage, Moss and code-check functions. Owner: Teammate B (P3).

Plain Python only: no agents here. The lead's agents call these functions.
Family directory lives in Moss (semantic search) when MOSS_PROJECT_ID/KEY are set,
otherwise in the local demo list below. Seed Moss once:  python -m services.data_tools seed
"""
import asyncio
import concurrent.futures
import hashlib
import hmac
import os
import sys
import threading
import time

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
MOSS_PROJECT_ID = os.getenv("MOSS_PROJECT_ID")
MOSS_PROJECT_KEY = os.getenv("MOSS_PROJECT_KEY") or os.getenv("MOSS_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

def hash_code(code: str) -> str:
    """Store this, never the plain code."""
    return hashlib.sha256(code.strip().encode()).hexdigest()


# Demo family, used to seed Moss and as a fallback when Moss isn't set up.
# Demo family: normal code 2580, danger code 7193 (same defaults as services/code_webhook.py's test mode).
# Put a teammate's real US phone number here (E.164, like +14155550123) for the demo call.
_FAKE_CONTACTS = {
    "arjun": {
        "name": "Arjun",
        "phone": os.getenv("DEMO_STUDENT_PHONE") or "+10000000000",
        "code_hash": hash_code("2580"),
        "danger_hash": hash_code("7193"),
        "relation": "son, college student",
        "aliases": ["AJ", "my son"],
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



# ---------- Family directory in Moss ----------
# Each family member is one Moss document. The text is what semantic search matches on
# (name, nicknames, relation); the metadata holds the phone and the HASHED codes, never the plain codes.
# Moss finds the best candidates, then we double-check the name is really one of that person's names,
# so "Priya" can never accidentally match Arjun and call the wrong person.
MOSS_INDEX = os.getenv("MOSS_INDEX") or "family-directory"
# The index and its search model are downloaded once and kept here, so restarts are fast.
MOSS_CACHE = os.getenv("MOSS_CACHE") or ".moss-cache"
_moss = None
_moss_loaded = threading.Event()
_moss_loading = threading.Lock()


def _run(coro, timeout: float = 20):
    """Run a Moss coroutine from plain sync code, even inside an agent's event loop."""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(asyncio.run, coro).result(timeout=timeout)
    finally:
        pool.shutdown(wait=False)  # don't hang if Moss is slow; the timeout already fired


def _moss_client():
    global _moss
    if _moss is None and MOSS_PROJECT_ID and MOSS_PROJECT_KEY:
        from moss import MossClient
        _moss = MossClient(MOSS_PROJECT_ID, MOSS_PROJECT_KEY, cache_path=MOSS_CACHE)
    return _moss


def _load_moss_index() -> None:
    """Download/load the index (slow the first time). Safe to call from many threads."""
    if _moss_loaded.is_set() or not _moss_loading.acquire(blocking=False):
        return
    try:
        started = time.time()
        asyncio.run(_moss_client().load_index(MOSS_INDEX, cache_path=MOSS_CACHE))
        _moss_loaded.set()
        print(f"[Moss] family directory loaded in {time.time() - started:.0f}s")
    except Exception as e:
        print(f"[Moss] could not load the index: {e}. Using the local demo list for now.")
    finally:
        _moss_loading.release()


def warm_moss() -> None:
    """Start loading Moss in the background. Lookups use the local demo list until it's ready."""
    if _moss_client() is not None and not _moss_loaded.is_set():
        threading.Thread(target=_load_moss_index, daemon=True).start()


def _doc_for(contact: dict):
    from moss import DocumentInfo
    aliases = [a.strip().lower() for a in contact.get("aliases", []) if a.strip()]
    aliases = sorted({contact["name"].lower(), *aliases})
    text = f"{contact['name']}. {contact.get('relation', 'family member')}. Also called: {', '.join(aliases)}."
    return DocumentInfo(
        id=contact["name"].lower(),
        text=text,
        metadata={
            "name": contact["name"],
            "aliases": ",".join(aliases),
            "phone": contact["phone"],
            "code_hash": contact["code_hash"],
            "danger_hash": contact.get("danger_hash", ""),
        },
    )


def seed_moss() -> None:
    """Create (or refresh) the Moss index with the demo family. Run once: python -m services.data_tools seed"""
    client = _moss_client()
    if client is None:
        raise SystemExit("Set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in .env first")
    docs = [_doc_for(c) for c in _FAKE_CONTACTS.values()]
    existing = {i.name for i in _run(client.list_indexes())}
    if MOSS_INDEX in existing:
        from moss import MutationOptions
        _run(client.add_docs(MOSS_INDEX, docs, MutationOptions(upsert=True)))
    else:
        _run(client.create_index(MOSS_INDEX, docs))
    print(f"Moss index '{MOSS_INDEX}' has {len(docs)} family member(s)")


def _moss_lookup(name: str) -> dict | None:
    """Best Moss match whose names really include `name`. None if Moss is off, still loading, or fails."""
    client = _moss_client()
    if client is None:
        return None
    if not _moss_loaded.is_set():
        warm_moss()  # never block a live case on the first download
        return None
    try:
        from moss import QueryOptions
        result = _run(client.query(MOSS_INDEX, name, QueryOptions(top_k=3, alpha=0.5)))
        wanted = name.strip().lower()
        for doc in result.docs:
            meta = doc.metadata or {}
            if wanted in meta.get("aliases", "").split(","):
                return meta
        return {}  # Moss answered: nobody by that name
    except Exception as e:
        print(f"[Moss] {e}. Falling back to the local demo list.")
        return None


def _find(name: str) -> dict:
    found = _moss_lookup(name)
    if found is None:  # Moss not set up or unreachable: use the local demo list
        contact = _FAKE_CONTACTS.get(name.strip().lower())
        if not contact:
            contact = next((c for c in _FAKE_CONTACTS.values()
                            if name.strip().lower() in [a.lower() for a in c.get("aliases", [])]), {})
        return contact
    return found


def save_contact(name: str, phone: str, code: str, danger_code: str = "",
                 relation: str = "family member", aliases: list[str] | None = None) -> None:
    """Save a family member's phone and HASHED codes (Moss if set up, plus the local list)."""
    contact = {"name": name, "phone": phone, "code_hash": hash_code(code),
               "danger_hash": hash_code(danger_code) if danger_code else "",
               "relation": relation, "aliases": aliases or []}
    _FAKE_CONTACTS[name.lower()] = contact
    client = _moss_client()
    if client is not None:
        from moss import MutationOptions
        _run(client.add_docs(MOSS_INDEX, [_doc_for(contact)], MutationOptions(upsert=True)))


def get_contact(name: str) -> dict:
    """Look up a family member. Returns {"name", "phone"} or {} if not found."""
    contact = _find(name)
    return {"name": contact.get("name"), "phone": contact.get("phone")} if contact else {}


def check_code(name: str, code: str) -> bool:
    """True only if the code matches the stored normal-code hash."""
    return classify_code(name, code) == "normal"


def classify_code(name: str, code: str) -> str:
    """Returns "normal", "danger" or "wrong" for the digits a student entered.

    Compares hashes in constant time so timing doesn't leak which code was close.
    """
    contact = _find(name)
    if not contact:
        return "wrong"
    entered = hash_code(code)
    if hmac.compare_digest(entered, contact["code_hash"]):
        return "normal"
    if contact.get("danger_hash") and hmac.compare_digest(entered, contact["danger_hash"]):
        return "danger"
    return "wrong"


if __name__ == "__main__":
    if sys.argv[1:] == ["seed"]:
        seed_moss()
    if _moss_client():
        print("Loading the Moss index (the first time can take a few minutes on slow Wi-Fi)...")
        _load_moss_index()
    print("source:", "Moss" if _moss_loaded.is_set() else "local demo list")
    print(get_contact("Arjun"), get_contact("AJ"), get_contact("Priya"))
    print("normal:", classify_code("Arjun", "2580"), "| danger:", classify_code("Arjun", "7193"),
          "| wrong:", classify_code("Arjun", "1111"))
    print(get_voice_note("note-1"))
