"""Messages the Family Shield agents send each other.

Everyone builds against this file. Tell the team before changing it.
The check code itself never reaches the Guardian: only ok=True/False.
"""
from uagents import Model


# Guardian -> Voice Analyst
class Analyze(Model):
    case_id: str
    note_id: str


# Voice Analyst -> Guardian
class Claims(Model):
    case_id: str
    claimed_identity: str
    amount: str
    story: str
    transcript: str


# Guardian -> Family agent
class GetFamily(Model):
    case_id: str
    student_name: str


# Family agent -> Guardian
class Contact(Model):
    case_id: str
    student_name: str
    phone: str


# Guardian -> Verifier: send the outreach voice message
class ReachStudent(Model):
    case_id: str
    student_name: str
    phone: str


# Verifier -> Guardian: was the message delivered?
class Reached(Model):
    case_id: str
    delivered: bool


# Guardian -> Verifier: the student typed a code in ASI:One
class CheckCode(Model):
    case_id: str
    student_name: str
    code: str


# Verifier -> Guardian
class CodeResult(Model):
    case_id: str
    ok: bool
    time: str
