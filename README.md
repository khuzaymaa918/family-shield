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

Built at **Cal Hacks 13.0**.

---

## How it works

1. **The parent tells Family Shield what happened** in ASI:One: *"I got a voice note from Arjun asking for money."*
2. **Family Shield replies instantly:** *Don't send any money yet. I'm checking with Arjun.*
3. **Behind the scenes, five agents work together:**
   - **Voice Inspector** downloads the voice note, transcribes it (Cartesia) and pulls out the claims (Claude).
   - **Scam Intel** compares the story with real scam reports collected by **Apify**, stored in **Moss**, and
     **Claude** names the pattern (e.g. *fake arrest + urgent bail money + secrecy*).
   - **Trusted Contacts** finds Arjun's **saved, verified** number in Moss. Never a number from the message.
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

*Demo family: Arjun, check code `2580`. Save the verifier's number as a contact so iPhone call screening
doesn't intercept the call.*

## Sponsor technology

| Sponsor | How Family Shield uses it |
| --- | --- |
| **Fetch.ai** | 5 uAgents on Agentverse (mailbox), Agent Chat Protocol, ASI:One interactive cards with a Check result button |
| **Anthropic Claude** | Reads the parent's message, extracts the voice note's claims, names the scam pattern |
| **Cartesia** | Speech-to-text for the voice note; an outbound voice agent that collects the keypad code and the 1/2 answer through webhook tools |
| **Moss** | Semantic family directory (nicknames like "AJ" or "my son" still match) and a second index of real scam reports |
| **Apify** | Google Search Scraper collects real news, government and consumer-alert reports about voice-clone family-emergency scams |
| **Supabase** | Storage for voice notes (`voice-notes` bucket) |

## Safety by design

- **The code always comes first.** Whoever picks up can't just press 1 or 2.
- **We only call saved, verified numbers.** Unknown names are never matched to someone else, so a scammer can't redirect the call.
- **Check codes are stored only as hashes,** compared in constant time, and never read back on the call.
- **Nothing decides except the student's answer.** Claude, the transcript, the scam-pattern check and how real the voice sounds are information only.
- **We never tell a parent to send money,** only whether the request really came from their child.
- **Every call says it's an AI** calling for the family.
- **Loop guard:** Family Shield ignores other AI assistants replying in the chat, so agents can't trigger calls by talking to each other.

## Run it yourself

```bash
git clone https://github.com/khuzaymaa918/family-shield.git
cd family-shield
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # fill in your keys; never commit .env
```

One-time setup:

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

## Team

Built at Cal Hacks 13.0 by Khuzayma Mushtaq, Jione Park, Byungwook Kang and Oluwamurewa Fadare.
