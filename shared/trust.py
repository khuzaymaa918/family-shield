"""Who our agents take messages from.

Agent addresses are public (README, Agentverse), so without these checks anyone could ask the Family agent
for a student's number, make the Verifier call any phone, or send the Guardian a fake result.
An expected address that isn't configured lets everything through, so a missing setting never blocks the flow.
"""
import os

from dotenv import load_dotenv
from uagents.crypto import Identity

load_dotenv()


def guardian_address() -> str:
    """GUARDIAN_ADDRESS, or the address GUARDIAN_SEED gives (same .env on the laptop running the agents)."""
    address = (os.getenv("GUARDIAN_ADDRESS") or "").strip()
    seed = os.getenv("GUARDIAN_SEED")
    if not address and seed:
        address = Identity.from_seed(seed, 0).address  # what uagents.Agent(seed=...) uses
    return address


def _bare(address: str) -> str:
    # uagents accepts "agent://agent1q..." or "test-agent://agent1q..." when sending, but the sender we
    # receive is always the bare agent1q... address.
    return address.strip().split("://")[-1]


def trusted(sender: str, expected: str) -> bool:
    return not expected or _bare(sender) == _bare(expected)
