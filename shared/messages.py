"""Messages the Family Shield agents send each other.

Everyone builds against this file. Tell the team before changing it.
The check code itself never reaches the Guardian: only the outcome of the call.
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


# Verifier -> Guardian: the outcome of the verification call. result is one of:
#   "sent"      -> right check code, and the student confirmed they DID send the message
#   "not_sent"  -> right check code, and the student said they did NOT send it: a scam
#   "wrong"     -> wrong check code twice: not confirmed
#   "no_answer" -> right code, but no clear 1/2 answer: not confirmed
class CodeResult(Model):
    case_id: str
    result: str
    time: str
