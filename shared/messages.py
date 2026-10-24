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


# Verifier -> Guardian: what the student entered on the keypad during the call.
# result is one of:
#   "normal" -> right check code: the student is confirmed
#   "danger" -> the danger code: silent alarm, the student may be under pressure
#   "wrong"  -> neither code after a retry: stay NOT_CONFIRMED
# The student hears the same reply for "normal" and "danger", so a bystander can't tell them apart.
class CodeResult(Model):
    case_id: str
    result: str
    time: str
