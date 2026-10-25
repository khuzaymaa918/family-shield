"""ASI:One interactive cards for Family Shield.

The Guardian (or a test agent) includes these content blocks in a ChatMessage.
A parent sees a coloured card instead of plain text. Tapping "Check result"
sends {"action": "status"} back so they don't have to type it.

result_card(result, name, time) — result is one of:
  "it_was_him"    — green: the student confirmed they sent the message
  "scam"          — red: the student confirmed they did not send it
  "not_confirmed" — yellow: we couldn't reach them or check the code

progress_card(name) — "Calling {name} now..." with a Check result button.

If ASI:One rejects the card payload it still shows the TextContent, so that
text has to make sense on its own.
"""
import json

from uagents_core.contrib.protocols.chat import MetadataContent, TextContent

RESULTS = {
    "it_was_him": {
        "emoji": "🟢",
        "heading": "{name} confirmed they sent it",
        "explanation": (
            "The request really came from {name}. "
            "Talk to them directly before sending anything."
        ),
        "badge": "Confirmed",
        "badge_variant": "success",
        "plain": (
            "🟢 {name} confirmed they sent it at {time}. "
            "The request really came from {name}. "
            "Talk to them directly before sending anything."
        ),
    },
    "scam": {
        "emoji": "🔴",
        "heading": "Scam: {name} did not send this",
        "explanation": "Do not send money to whoever contacted you.",
        "badge": "Scam",
        "badge_variant": "warning",
        "plain": (
            "🔴 Scam: {name} did not send this (checked at {time}). "
            "Do not send money to whoever contacted you."
        ),
    },
    "not_confirmed": {
        "emoji": "🟡",
        "heading": "Not confirmed",
        "explanation": (
            "We couldn't confirm it was {name}. Don't send money. "
            "Call them on a number you already know."
        ),
        "badge": "Not confirmed",
        "badge_variant": "info",
        "plain": (
            "🟡 Not confirmed. We couldn't confirm it was {name} "
            "(last check at {time}). Don't send money. "
            "Call them on a number you already know."
        ),
    },
}


def _card(text: str, payload: dict, terminal: bool) -> list:
    """One text bubble plus one ASI:One card declaration."""
    metadata = {
        "card_protocol_version": "1",
        "requires_card_interaction": "true",
        "card_kind": "custom",
        "card_payload": json.dumps(payload),
        "preferred_drawer_width_px": "540",
    }
    if terminal:
        metadata["is_terminal"] = "true"
    return [
        TextContent(type="text", text=text),
        MetadataContent(metadata=metadata),
    ]


def result_card(result: str, name: str, time: str) -> list:
    """Green / red / yellow card for a finished check."""
    spec = RESULTS.get(result)
    if spec is None:
        raise ValueError(
            f"result must be one of {sorted(RESULTS)}, got {result!r}"
        )
    heading = spec["heading"].format(name=name)
    explanation = spec["explanation"].format(name=name)
    payload = {
        "root": {
            "type": "section",
            "title": f"{spec['emoji']} {heading}",
            "children": [
                {"type": "badge", "label": spec["badge"], "variant": spec["badge_variant"]},
                {"type": "text", "value": explanation, "style": "body"},
                {"type": "text", "value": f"Checked at {time}", "style": "muted"},
            ],
        }
    }
    return _card(spec["plain"].format(name=name, time=time), payload, terminal=True)


def progress_card(name: str) -> list:
    """In-progress card with a button that sends {"action": "status"}."""
    text = f"Calling {name} now… Please don't send any money yet."
    payload = {
        "root": {
            "type": "section",
            "title": f"Calling {name} now…",
            "subtitle": "Please don't send any money yet.",
            "children": [
                {
                    "type": "text",
                    "value": (
                        f"I'm checking with {name} on the number your family verified. "
                        "Tap Check result when you want the latest update."
                    ),
                    "style": "body",
                },
                {
                    "type": "button",
                    "label": "Check result",
                    "primary": True,
                    "action": {"selection": {"action": "status"}},
                },
            ],
        }
    }
    return _card(text, payload, terminal=False)


if __name__ == "__main__":
    demos = [
        ("it_was_him", result_card("it_was_him", "Arjun", "3:42 PM")),
        ("scam", result_card("scam", "Arjun", "3:42 PM")),
        ("not_confirmed", result_card("not_confirmed", "Arjun", "3:42 PM")),
        ("progress", progress_card("Arjun")),
    ]
    for label, content in demos:
        print(f"\n=== {label} ===")
        for item in content:
            if isinstance(item, TextContent):
                print("text:", item.text)
            else:
                print("kind:", item.metadata["card_kind"])
                print("terminal:", item.metadata.get("is_terminal", "false"))
                print(json.dumps(json.loads(item.metadata["card_payload"]), indent=2))
