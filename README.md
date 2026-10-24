# Family Shield

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Scammers clone a student's voice and message their parents: "I've been arrested, send money now."
Family Shield is a team of Fetch.ai agents, used entirely through ASI:One, that analyzes the
suspicious voice message, reaches the real student, and tells the parent whether the student
confirmed with their check code. Until then, the answer is always: don't send money.

Built at Cal Hacks 13.0 for international students in the US and their parents back home.

## Agents

| Agent | Job | Agentverse address |
| --- | --- | --- |
| Guardian | Talks to parents and students in ASI:One, coordinates everything | _add after registering_ |
| Voice Analyst | Fetches the stored voice note, transcribes it, extracts the claims | _add after registering_ |
| Family agent | Holds the student's verified phone and hashed check code (Moss) | _add after registering_ |
| Verifier | Sends the Cartesia voice message, checks the student's code | _add after registering_ |

Tools: Fetch.ai uAgents + Agentverse + ASI:One, Claude, Cartesia, Moss, Supabase Storage.

## Setup

```bash
git clone <repo link>
cd family-shield
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # add your own keys; never commit .env
```

Run an agent from the repo root, e.g.:

```bash
python -m agents.guardian.agent
```

Test a teammate's functions on their own:

```bash
python -m services.cartesia_tools
python -m services.data_tools
```

## Team workflow

- Never work on `main`. One branch per task: `p<your number>/<task>`
  - Lead: `p1/guardian-asi-one`
  - Teammate A: `p2/transcribe`
  - Teammate B: `p3/supabase-storage`
  - Teammate C: `p4/readme`
- Before a new branch: `git checkout main && git pull`
- When it works: push and open a Pull Request into `main`
- Only edit your own files: Teammate A `services/cartesia_tools.py`, Teammate B `services/data_tools.py`
- Never commit `.env` or API keys
- Don't change `shared/messages.py` without telling the team
- Keep function names, inputs and outputs the same; the agents depend on them

## Sample voice notes

| ID | Description |
| --- | --- |
| note-1 | _add_ |
| note-2 | _add_ |
| note-3 | _add_ |

## Rules the product follows

- "Confirmed" only after the student enters the right code; a roommate's word or a schedule never confirms.
- Every voice message says it's an AI calling for the parent; everyone contacted agrees at setup.
- We report what we confirmed, never "this is a scam".
