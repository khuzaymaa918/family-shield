"""One-time Cartesia setup for deliver_voice_message. Owner: Teammate A (P2).

Creates (or updates) the verify_code webhook tool and configures the call agent: it greets with our message,
collects the check code from the keypad, sends it to services/code_webhook.py, and never reads it back.
Prints the two IDs to put in .env yourself. It never prints the API key or the webhook secret.

Needs in .env: CARTESIA_API_KEY, CODE_WEBHOOK_URL (public https base, e.g. a cloudflared tunnel) and
CODE_WEBHOOK_SECRET. Rerun it whenever CODE_WEBHOOK_URL changes.

    python -m services.cartesia_setup                       # configure "family-shield-verifier"
    python -m services.cartesia_setup --agent other-name
    python -m services.cartesia_setup --model <model id>    # pick a specific LLM from the printed list
    python -m services.cartesia_setup --provision-number    # get a Cartesia US number if you have none
    python -m services.cartesia_setup --recent-calls        # transcripts; agent_hangup means it ended itself
"""
import argparse
import os
import sys

import requests

from services.cartesia_tools import CARTESIA_API, _headers

TOOL_NAME = "verify_code"

INSTRUCTIONS = """You are Family Shield's Verifier, an AI assistant on a phone call for the student's family.
Your welcome message already asked the student to enter their check code on the keypad.

Rules:
- The check code is 4 digits. When the student enters 4 digits on the keypad (or says them), call verify_code
  with exactly those digits.
- After you ask for the code again, wait for NEW digits. Send only digits entered after your latest request.
  Never send digits from earlier in the call again.
- Never read back, repeat or confirm the digits. Never say whether a code was right or wrong. Never mention
  that there is more than one code.
- If verify_code returns "retry", say only: "That didn't go through. Please enter your check code again."
- When verify_code returns "recorded", say only: "Thanks, I'll let your family know." Then end the call.
- If they ask who you are, say you're an AI assistant calling for their family, then ask for the code again.
- Never ask for or share any other personal information."""

# The agent only acts after the student types or speaks. Remind them once, then hang up if nothing comes
# (Cartesia's default of 240s kept a silent call open for 4 minutes).
CHECK_IN_SECS = 10
SILENT_HANGUP_SECS = 30


def _get(path: str, **params) -> dict | list:
    response = requests.get(f"{CARTESIA_API}{path}", headers=_headers(), params=params, timeout=30)
    if not response.ok:
        sys.exit(f"GET {path} failed ({response.status_code}): {response.text[:300]}")
    return response.json()


def _items(body: dict | list) -> list:
    return body if isinstance(body, list) else body.get("data", [])


def find_agent(name: str) -> dict:
    agents = _items(_get("/v1/agents", limit=100))
    match = next((a for a in agents if a.get("name") == name), None)
    if match is None:
        sys.exit(f"No agent named {name!r}. Found: {[a.get('name') for a in agents]}")
    return match


def claude_models() -> list[dict]:
    models = _items(_get("/v1/agents/models", limit=100))
    claude = [m for m in models if "claude" in f"{m.get('id')} {m.get('display_name')}".lower()]
    if not claude:
        sys.exit(f"No Claude model in the catalog. Available: {[m.get('id') for m in models]}")
    # Fastest first: on a phone call, latency matters more than anything else.
    return sorted(claude, key=lambda m: m.get("average_latency_ms") or 10**9)


def ensure_tool(webhook_url: str, secret: str) -> str:
    """Creates the verify_code webhook tool, or points the existing one at the current URL."""
    tool = {
        "type": "webhook",
        "name": TOOL_NAME,
        "description": "Sends the check code the student entered. Use it every time they enter or say a code.",
        "pre_tool_speech": "off",
        "execution_mode": "immediate",
        "response_timeout_secs": 10,
        "api_schema": {
            "url": f"{webhook_url.rstrip('/')}/tools/verify_code",
            "method": "POST",
            "request_body_schema": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string", "dynamic_variable": "case_id"},
                    "code": {"type": "string", "description": "The digits the student entered, digits only."},
                },
                "required": ["code"],
            },
            "authentication": {"mode": "bearer", "token": {"type": "secret", "secret_value": secret}},
        },
    }
    existing = next((t for t in _items(_get("/v1/agents/tools", limit=100)) if t.get("name") == TOOL_NAME), None)
    if existing:
        response = requests.patch(
            f"{CARTESIA_API}/v1/agents/tools/{existing['id']}",
            headers=_headers(),
            json={k: tool[k] for k in ("description", "api_schema")},
            timeout=30,
        )
    else:
        response = requests.post(f"{CARTESIA_API}/v1/agents/tools", headers=_headers(), json=tool, timeout=30)
    if not response.ok:
        # The request carried the webhook secret; never echo it back if Cartesia's error repeats the input.
        sys.exit(f"Saving the {TOOL_NAME} tool failed ({response.status_code}): {response.text.replace(secret, '***')[:500]}")
    return existing["id"] if existing else response.json()["id"]


def configure(agent_id: str, model_id: str, tool_id: str) -> None:
    config = {
        "initial_message": "{{message}}",
        "instructions": INSTRUCTIONS,
        "language": {"primary": "en"},
        "model": {"id": model_id},
        "tools": [{"id": tool_id}],
        # {} turns a system tool on with Cartesia's defaults.
        "system_tools": {"end_call": {}, "voicemail_detection": {}},
        "turn": {"inactivity_end_call_secs": SILENT_HANGUP_SECS, "inactivity_check_in_secs": CHECK_IN_SECS},
    }
    response = requests.patch(
        f"{CARTESIA_API}/v1/agents/{agent_id}", headers=_headers(), json={"config": config}, timeout=30
    )
    if not response.ok:
        sys.exit(f"Updating the agent failed ({response.status_code}): {response.text[:500]}")


def phone_numbers(provision: bool) -> list[dict]:
    numbers = _items(_get("/agents/phone-numbers"))
    if not numbers and provision:
        response = requests.post(
            f"{CARTESIA_API}/agents/phone-numbers/provision",
            headers=_headers(),
            json={"label": "family-shield"},
            timeout=30,
        )
        if not response.ok:
            sys.exit(f"Provisioning a number failed ({response.status_code}): {response.text[:300]}")
        numbers = _items(_get("/agents/phone-numbers"))
    return numbers


def recent_calls(agent_id: str, limit: int = 5) -> None:
    for call in _items(_get("/agents/calls", agent_id=agent_id, limit=limit, expand="transcript")):
        print(f"{call.get('start_time')}  status={call.get('status')}  end_reason={call.get('end_reason')}")
        for turn in call.get("transcript") or []:
            print(f"    {turn.get('role')}: {turn.get('text')}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", default="family-shield-verifier")
    parser.add_argument("--model", help="LLM id; defaults to the fastest Claude model in the catalog")
    parser.add_argument("--provision-number", action="store_true")
    parser.add_argument("--recent-calls", action="store_true", help="show the last calls instead of configuring")
    args = parser.parse_args()

    agent = find_agent(args.agent)
    if args.recent_calls:
        recent_calls(agent["id"])
        return
    models = claude_models()
    print("Claude models (fastest first):")
    for m in models:
        print(f"  {m.get('id')}  ({m.get('display_name')}, ~{m.get('average_latency_ms')} ms)")
    model_id = args.model or models[0]["id"]

    webhook_url, secret = os.getenv("CODE_WEBHOOK_URL"), os.getenv("CODE_WEBHOOK_SECRET")
    if not (webhook_url and webhook_url.startswith("https://") and secret):
        sys.exit("Set CODE_WEBHOOK_URL (public https://...) and CODE_WEBHOOK_SECRET in .env first")
    tool_id = ensure_tool(webhook_url, secret)
    configure(agent["id"], model_id, tool_id)
    print(
        f"\nConfigured {args.agent!r}: model {model_id}, tool {TOOL_NAME} -> {webhook_url.rstrip('/')}/tools/verify_code, "
        f"check-in after {CHECK_IN_SECS}s, hangs up after {SILENT_HANGUP_SECS}s of silence"
    )

    numbers = phone_numbers(args.provision_number)
    if not numbers:
        print("\nNo phone number yet. Rerun with --provision-number, or add one in the Playground.")
    for n in numbers:
        print(f"Number {n.get('number')}  label={n.get('label')}  id={n.get('id')}")

    print("\nPut these in .env yourself:")
    print(f"CARTESIA_AGENT_ID={agent['id']}")
    if numbers:
        print(f"CARTESIA_FROM_NUMBER_ID={numbers[0].get('id')}")


if __name__ == "__main__":
    main()
