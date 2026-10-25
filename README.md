# Family Shield

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Scammers can now clone a student's voice, impersonate them, and trick their family into losing money. Family Shield is a team of Fetch.ai agents, used entirely through ASI:One, that checks a suspicious call or voice message with the real student before the family sends anything.

Built at Cal Hacks 13.0 for international students in the US and their families back home.

## The problem

Parents and grandparents of students who live far away get calls and voice notes that sound exactly like their child. The caller asks for bail, tuition, or a hospital payment the same day, often from a number the family doesn't recognize, and asks them not to tell anyone. A parent can't tell a cloned voice from their real child just by listening, and the pressure to act fast is the whole trick. Calling the child back isn't always possible either, especially across time zones.

## What Family Shield does

A parent tells Family Shield in ASI:One that someone claiming to be their child is asking for money. Family Shield tells them not to send anything yet and places a phone call to the number the family verified ahead of time. The call says it is an AI assistant and asks the student to type their family check code on the keypad. When the parent asks for the status, Family Shield tells them whether the real student answered with the right code. The decision never depends on how convincing the voice sounded. It depends only on the code typed on the student's own phone.

## Walkthrough

Priya gets a call from someone who sounds exactly like her son Arjun. He says he has been arrested and needs $2,000 for bail tonight, and asks her not to tell his father. She opens Family Shield in ASI:One and writes that someone claiming to be Arjun just called asking for bail money, and adds the ID of the call recording.

Family Shield answers right away: "Don't send any money yet. I'm checking with Arjun directly now." It lists the warning signs it noticed, such as urgency and secrecy. Behind the scenes, the Voice Analyst transcribes the recording and picks out who it claims to be, how much it asks for, and the story. The Family agent looks up the phone number the family verified for Arjun.

Arjun's phone rings. A voice says: "Hi, this is Family Shield, an AI assistant calling for your family. Someone sent them a message claiming to be you. Please enter your check code on your phone's keypad now." Arjun types his four-digit code. The assistant never repeats the digits, never says whether they were right, and says only, "Thanks, I'll let your family know."

Priya types "status." Family Shield replies: "🟢 CONFIRMED. Arjun entered your family check code at 3:42 PM. Arjun is safe and did not send that message. Do not send money to whoever contacted you."

Other endings:

- **🟡 Not confirmed.** The student entered a wrong code twice, didn't enter one within three minutes, couldn't be reached, or has no verified number. The parent is told not to send money and to contact their child on a number they already know.
- **🔴 Danger signal.** The student entered their separate danger code. The call sounds exactly the same to anyone next to them. The parent is told the student may not be able to talk freely and to call 911.

## Technical features

- **Four cooperating agents.** The Guardian, Voice Analyst, Family agent, and Verifier are built with Fetch.ai uAgents, registered on Agentverse through mailboxes, and send each other typed messages defined in `shared/messages.py`.
- **ASI:One Chat Protocol.** The Guardian is the only agent the parent talks to. It keeps one open case per parent and answers status requests with the latest result.
- **Claude intake and claim extraction.** Claude reads the parent's message for the child's name, any recording ID, and warning signs. It reads the call transcript for the claimed identity, amount, and story. Both have regex fallbacks if the Claude call fails.
- **Cartesia speech-to-text.** The Voice Analyst transcribes the uploaded call recording with `ink-whisper`.
- **Cartesia outbound voice agent.** The Verifier places a real phone call, discloses that it is an AI, and collects the check code from the keypad. It hangs up after 30 seconds of silence.
- **Keypad code webhook.** A FastAPI endpoint, exposed through a tunnel, receives the digits. It checks a bearer secret, normalises digits from other scripts to 0 to 9, and never logs the code.
- **Hashed codes with a silent danger code.** Codes are stored as SHA-256 hashes and compared in constant time. The normal code and the danger code get identical spoken replies, so a bystander can't tell them apart.
- **One hard confirmation rule.** Only a correct code reported by the Verifier can mark a case confirmed. Claude, the transcript, the parent, and a timeout cannot.
- **Safe timeouts.** If no code arrives within `CODE_TIMEOUT_SECONDS` (180 by default), the case ends as not confirmed, never as confirmed.
- **Supabase Storage.** Call recordings are fetched from the `voice-notes` bucket by ID.
- **Moss (in progress).** Verified contacts and code hashes are meant to live in Moss. Until then, they are held in memory in `services/data_tools.py`.

## Agents

| Agent | Job | Port | Agentverse address |
| --- | --- | --- | --- |
| Guardian | Talks to the parent in ASI:One and coordinates the case | 8000 | _add after registering_ |
| Voice Analyst | Fetches the call recording, transcribes it, extracts the claims | 8001 | _add after registering_ |
| Family agent | Returns the student's verified phone number | 8002 | _add after registering_ |
| Verifier | Calls the student and checks the keypad code | 8003 | _add after registering_ |

## Run it locally

You need Python 3.11 or newer, [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/), and API keys for Cartesia, Anthropic, and Supabase.

### 1. Install

```bash
git clone https://github.com/khuzaymaa918/family-shield.git
cd family-shield
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # add your own keys; never commit .env
```

### 2. Fill in `.env`

Set a different long random string for each of `GUARDIAN_SEED`, `VOICE_ANALYST_SEED`, `FAMILY_SEED`, and `VERIFIER_SEED`. A seed decides the agent's address, so keep it the same between runs. Add `CARTESIA_API_KEY`, `ANTHROPIC_API_KEY`, `SUPABASE_URL`, and `SUPABASE_KEY`. Set `DEMO_STUDENT_PHONE` to the US phone number that should receive the verification call, in the form `+14155550123`.

### 3. Open a public tunnel for the keypad webhook

In its own terminal, leave this running:

```bash
cloudflared tunnel --url http://localhost:8090
```

Copy the `https://...trycloudflare.com` URL into `.env` as `CODE_WEBHOOK_URL`, and set `CODE_WEBHOOK_SECRET` to a long random string.

### 4. Configure the Cartesia call agent

```bash
python -m services.cartesia_setup
```

Copy the `CARTESIA_AGENT_ID` and `CARTESIA_FROM_NUMBER_ID` it prints into `.env`. If you don't have a Cartesia phone number yet, add `--provision-number`. Rerun this step whenever the tunnel URL changes.

### 5. Start the agents

Start each agent in its own terminal, from the repo root. Start the three workers first, and copy each `agent1q...` address they print into `.env` as `VOICE_ANALYST_ADDRESS`, `FAMILY_ADDRESS`, and `VERIFIER_ADDRESS`.

```bash
python -m agents.voice_analyst.agent
python -m agents.family.agent
python -m agents.verifier.agent
```

Then start the Guardian:

```bash
python -m agents.guardian.agent
```

The first time each agent starts, open the Agentverse inspector link it prints and connect it with **Mailbox**.

### 6. Try it

Find the Guardian in ASI:One by its address and tell it that someone claiming to be your child asked for money. Type "status" at any point to see the latest result.

### Testing pieces on their own

```bash
python -m services.data_tools              # storage, contacts and code checks
python -m services.claude_tools            # Claude intake and claim extraction
python -m services.cartesia_tools          # transcribe and generate the outreach audio
python -m services.cartesia_tools +14155550123   # also place a real verification call
python -m services.code_webhook            # keypad webhook with test codes
python -m services.cartesia_setup --recent-calls # transcripts of the last verification calls
```

## Privacy and safety

Family Shield never calls a message a scam on the parent's behalf, never tells a parent to send money, and every call it places says it is an AI assistant. Check codes are stored only as hashes, never reach the Guardian, are never read back on the call, and are not written to logs. Never commit `.env`.