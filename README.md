# 🛡️ Family Shield

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**Check with your kid before you pay.**

Scammers clone a student's voice from a few seconds of video and send their parents an urgent voice note:
*"Mom, I've been arrested, I need bail money tonight, don't tell Dad."* It sounds exactly like them.

Family Shield is a team of five **Fetch.ai agents**, used entirely through **ASI:One**, that reaches the real
student on their saved number and gets an answer only they can give, before the parent sends a cent.

> In 2025 Americans reported losing **$3.5 billion** to impostor scams, the most-reported fraud category
> ([FTC](https://ftc.gov/news-events/news/press-releases/2026/06/ftc-data-show-people-reported-losing-3-point-5-billion-imposter-scams-2025)),
> and people 60+ lost **$7.7 billion** to fraud, up 59% (FBI IC3 2025). The FBI now describes "distress"
> scams that use **voice cloning** to imitate family members.

Built at **Cal Hacks 13.0** for **international students in the US and their parents back home**. The parent
is in another time zone and can't drop by campus, so a panicked "I need money tonight" is hard to check.

---

## How it works

1. **The parent tells Family Shield what happened** in ASI:One: *"I got a voice note from Arjun asking for money."*
2. **Family Shield replies instantly:** *Don't send any money yet. I'm checking with Arjun.*
3. **Behind the scenes, five agents work together:**
   - **Voice Inspector** downloads the voice note, transcribes it (Cartesia) and pulls out the claims (Claude).
   - **Scam Intel** compares the story with real scam reports collected by **Apify**, stored in **Moss**, and
     **Claude** names the pattern (e.g. *fake arrest + urgent bail money + secrecy*).
   - **Trusted Contacts** finds the number the family **registered** for Arjun, in Moss. Never a number from
     the message.
   - **Callback Verifier** calls Arjun with a calm **Cartesia** voice agent. He enters his **family check code**
     on the keypad, and only then is asked: *"Did you send your family a message asking for money? Press 1 for yes, 2 for no."*
4. **The parent taps "Check result"** and gets a clear answer:

| Result | Meaning |
| --- | --- |
| 🟢 **Request confirmed** | Arjun entered his code and confirmed he sent it. Talk to him directly (plus safe-payment advice). |
| 🔴 **Scam** | Arjun entered his code and confirmed he did **not** send it. Don't pay. |
| 🟡 **Not confirmed** | Wrong code, no answer, or no saved number. Don't pay yet. |

**The same voice note can be real or fake. We never judge by how real a voice sounds; only the student's
own answer, after their check code, decides.**

## Architecture

```
                         ┌──────────────── ASI:One (parent) ────────────────┐
                         │  "I got a voice note from Arjun asking for money" │
                         └──────────────────────────┬────────────────────────┘
                                                    │ Chat Protocol
                                     ┌──────────────▼──────────────┐
                                     │  🛡️ Family Shield (Guardian) │  Claude reads the message
                                     └──┬───────────┬───────────┬──┘
                       Analyze          │           │ CheckScam │ GetFamily / ReachStudent
            ┌───────────────────────────▼─┐   ┌─────▼─────────┐ │
            │ 🎙️ Voice Inspector           │   │ 🔍 Scam Intel  │ │
            │ Supabase → Cartesia STT →    │   │ Apify → Moss → │ │
            │ Claude claims                │   │ Claude pattern │ │
            └──────────────────────────────┘   └───────────────┘ │
                                     ┌──────────────────────────┴──────┐
                                     │ 👤 Trusted Contacts (Moss)       │──► verified number
                                     └──────────────────────────────────┘
                                     ┌──────────────────────────────────┐
                                     │ 📞 Callback Verifier (Cartesia)  │──► real phone call:
                                     └──────────────────────────────────┘    check code → "did you send it?" 1/2
```

## Agents (Agentverse)

| Agent | Job | Address |
| --- | --- | --- |
| 🛡️ **Family Shield** (Guardian), `@familyshield` | Talks to the parent in ASI:One, coordinates everything | `agent1qv67aefueva8rrgeyn8tfz53hzcj0dv838vj8gepesghu7mtc2qf6jwajgw` |
| 🎙️ **Voice Inspector** | Voice note → transcript → claims | `agent1qgrgc6tvrmu43snzkl7gcjwjf8jmphlzsy4sk2cyh22khpaj96thzky553l` |
| 👤 **Trusted Contacts** | Saved, verified numbers and hashed check codes (Moss) | `agent1q2y3jdsjpd24mnpu0t3qsjc0hupezhtexpdacyfs9lqpkqdumu84q93xe9a` |
| 📞 **Callback Verifier** | Calls the student, keypad code, "did you send it?" | `agent1q0neq6pmj5wfdne4ed3tdmkvkg68r2k4nvtscd3f7t28stjel2e72wgugg5` |
| 🔍 **Scam Intel** | Real scam reports (Apify + Moss), pattern named by Claude | `agent1qvhtup99x7ca30cnwua24sq6eafsgtkg7h85qx3qfmn6f7u03fx42sng2vn` |

## Try it in ASI:One

1. Open [asi1.ai](https://asi1.ai), start a chat, and message **`@familyshield`**.
2. After your first message, open **Chat Settings → AI responses → Mentions only**, so your personal AI
   doesn't answer on Family Shield's behalf.
3. Send: `@familyshield I got a voice note from Arjun asking for money`
4. When the verification call is done, tap **Check result** (or type `@familyshield status`). If the chat
   keeps showing "Reasoning…", refresh the page.

*Demo family: Arjun, check code `2580`, with a sample voice note. Save the verifier's number as a contact so
iPhone call screening doesn't intercept the call.*

## Sponsor technology

| Sponsor | How Family Shield uses it |
| --- | --- |
| **Fetch.ai** | 5 uAgents on Agentverse (mailbox), Agent Chat Protocol, ASI:One interactive cards with a Check result button |
| **Anthropic Claude** | Reads the parent's message, extracts the voice note's claims, names the scam pattern |
| **Cartesia** | Speech-to-text for the voice note; an outbound voice agent that collects the keypad code and the 1/2 answer through webhook tools. Features and limitations: [services/CARTESIA.md](services/CARTESIA.md) |
| **Moss** | Family directory that finds each family member by name or nickname ("AJ") and never matches a stranger, plus a second index of real scam reports searched by meaning |
| **Apify** | Google Search Scraper collects real news, government and consumer-alert reports about voice-clone family-emergency scams |
| **Supabase** | Storage for voice notes (`voice-notes` bucket) |

## Safety by design

- **The code always comes first.** Whoever picks up can't just press 1 or 2.
- **We only call numbers the family registered.** Unknown names are never matched to someone else, and a number in the scam message is never used, so a scammer can't redirect the call.
- **Check codes are stored only as hashes,** compared in constant time, and never read back on the call.
- **Unclear answers never turn red.** On the call only a clear 1/2 (or a plain yes/no) counts; anything else stays 🟡.
- **Nothing decides except the student's answer.** Claude, the transcript, the scam-pattern check and how real the voice sounds are information only.
- **We never tell a parent to send money,** only whether the request really came from their child.
- **Every call says it's an AI** calling for the family.
- **Loop guard:** Family Shield ignores other AI assistants replying in the chat, so agents can't trigger calls by talking to each other.

## Claude: where it helps and where it can fail

Claude reads the parent's message, pulls the claims out of the voice note, names the scam pattern, and runs
the phone conversation (inside the Cartesia agent). None of that decides the result. Where it can go wrong:

| If Claude... | What happens |
| --- | --- |
| reads the wrong name | Only saved names match. An unknown name gets 🟡, never a call to someone else |
| is down or returns bad JSON | A simple name guess takes over and the check still runs, without the warning signs |
| is steered by the scammer's own words in the voice note | The claims and the pattern text could be misleading. They are background only (the claims are shown as "this does NOT prove who it is") and never change the result |
| mishears or improvises on the call | Our server accepts the 1/2 answer only after a right code, keeps one result per case, and treats unclear answers as 🟡 |

**Building with Claude.** We wrote the agents and services with Claude Code; those commits are marked
`Co-Authored-By: Claude` in the history. Before submitting, separate Claude reviewers given only this repo
judged it against the sponsor rubrics. They found bugs we then fixed: a lone "help" started a check instead
of showing help, "no answer" on the call counted as "no" (a false 🔴), and tapping Check result after we
asked for the child's name opened a case for a child named "Status".

## Measuring impact

What we will track per case: the result (🟢 / 🔴 / 🟡), the time from the parent's message to a result, and
how far the check got (number found, call placed, code entered, question answered). The numbers that matter:
how often a parent gets 🟢 or 🔴 instead of 🟡, and how often that happens before the scammer's deadline
(minutes, not hours). Every result already shows these steps, with their times, as a timeline.

## Cartesia: the voice agent

Voice is the core of Family Shield: without the call, nothing is verified.

- **Managed Agent**, configured in code (`services/cartesia_setup.py`): greeting, instructions, Claude as the
  agent's LLM, tools, and turn settings (check in after 10s of silence, hang up after 30s).
- **Outbound calls** from our Cartesia number (`deliver_voice_message` in `services/cartesia_tools.py`).
- **Keypad input + webhook tools:** `verify_code` and `confirm_sent` send the code and the 1/2 answer to our
  server (`services/code_webhook.py`) behind a bearer secret. Nobody nearby hears the code.
- **Dynamic variables** (`message`, `case_id`): every call carries its own greeting and case.
- **System tools:** `end_call` and `voicemail_detection`, so the agent hangs up by itself and never leaves a
  code prompt on voicemail.
- **Speech-to-text** (`ink-whisper`) for the voice note, and **text-to-speech** (`sonic-3.6`) to compare
  voices before choosing Whitney, a calm, even voice for a worried student.

**Setup:** see [Run it yourself](#run-it-yourself). **Known limitations:** Cartesia numbers call US numbers
only; a quick cloudflared tunnel gets a new URL on every restart, so setup must be rerun; code-first and one
result per case are enforced by our server, while asking the 1/2 question relies on the agent's instructions.
Full details, including the call script: [services/CARTESIA.md](services/CARTESIA.md).

## Run it yourself

```bash
git clone https://github.com/khuzaymaa918/family-shield.git
cd family-shield
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # fill in your keys; never commit .env
```

One-time setup (first create a phone number and an agent named `family-shield-verifier` in the
[Cartesia Playground](https://play.cartesia.ai); the setup script configures it but doesn't create it):

```bash
cloudflared tunnel --url http://localhost:8090   # copy the https URL into CODE_WEBHOOK_URL
python -m services.cartesia_setup                # configures the Cartesia call agent
python -m services.data_tools seed               # family directory in Moss
python -m services.scam_intel seed               # scam reports: Apify → Moss
```

Start the agents (one terminal each, Guardian last):

```bash
python -m agents.verifier.agent
python -m agents.family.agent
python -m agents.voice_analyst.agent
python -m agents.scam_intel.agent
python -m agents.guardian.agent
```

Each agent prints its `agent1q...` address on start. Put those in `.env` (`VOICE_ANALYST_ADDRESS`,
`FAMILY_ADDRESS`, `VERIFIER_ADDRESS`, `SCAM_INTEL_ADDRESS`) before starting the Guardian.

## Team

Built at Cal Hacks 13.0 by Khuzayma Mushtaq, Jione Park, Byungwook Kang and Oluwamurewa Fadare.
