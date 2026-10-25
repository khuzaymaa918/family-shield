# Cartesia in Family Shield

Voice is how Family Shield reaches the real student. When a parent reports a suspicious "I've been arrested,
send money" message, a Cartesia voice agent calls the student's saved phone number. The student types their
family check code on the keypad, then answers one question: did you send that message? Without the call there
is no verification, so voice is the core of the product, not a demo feature.

## Cartesia features we use

| Feature | Where | What it does for us |
| --- | --- | --- |
| Managed Agents | `services/cartesia_setup.py` | The call agent: instructions, greeting, model, tools, turn settings, configured through `PATCH /v1/agents/{id}` |
| Phone numbers + outbound calls | `deliver_voice_message` in `services/cartesia_tools.py` | `POST /agents/calls` places the verification call from our US number |
| Claude as the agent's LLM | `cartesia_setup.py` picks the fastest Claude model in Cartesia's catalog | Runs the conversation on the call |
| Webhook tools | `verify_code` and `confirm_sent`, received by `services/code_webhook.py` | Send the typed code and the 1/2 answer to our server, tagged with the case, behind a bearer secret |
| Dynamic variables | `message`, `case_id` | Each call gets its own greeting and case ID |
| Keypad (DTMF) input | the student types the code and presses 1 or 2 | Nobody nearby hears the code |
| System tools | `end_call`, `voicemail_detection` | The agent hangs up by itself and doesn't leave a code prompt on voicemail |
| Turn settings | check-in after 10s, hang up after 30s of silence | A silent call doesn't stay open |
| Batch speech-to-text (`ink-whisper`) | `transcribe` | Turns the scam voice note into text for Claude to analyze. English in the demo; `transcribe` also takes `language="hi"` for Hindi notes |
| Text-to-speech (`sonic-3.6`) | `make_voice_message` | Renders the greeting as an mp3, so we could compare voices without placing calls |
| Voice | Whitney (`f3c7d5d2-c1e1-41a0-bd88-8b5512be5335`) | A calm, even voice for a student who may be worried. Picked from 7 calm voices |

## The call

1. "Hi, this is Family Shield, an AI assistant calling for your family. They just got a message that says
   it's from you, and they want to make sure you're okay. Please enter your four-digit check code on your
   phone's keypad now." (about 9 seconds before the code request)
2. The student types the code. The agent sends it with `verify_code` and never reads it back.
3. Wrong code: "That didn't go through. Please enter your check code again." One retry, then the case stays
   unconfirmed.
4. Right code: "Did you send your family a message asking for money? Press 1 for yes, or 2 for no." The agent
   sends the answer with `confirm_sent`. Only a clear 1/2 (or a plain yes/no) counts; anything unclear leaves
   the case unconfirmed instead of turning it red.
5. "Thanks, I'll let your family know." Then the agent ends the call.

The code always comes first, so whoever picks up the phone can't just press 1 or 2.

The earlier, code-only version of this call was tested with real calls on Oct 24: right code, a wrong code
followed by the right one, and keypad input during the greeting. Every call ended with `agent_hangup`.

## Setup

1. Account and credits: sign up at https://play.cartesia.ai, then use the Cal Hacks promo code
   `CARTESIACALHACKS` at checkout for the Startup plan.
2. Put `CARTESIA_API_KEY` in `.env` (from https://play.cartesia.ai/keys). Never commit it.
3. In the Playground, create an agent named `family-shield-verifier` and a phone number (or let
   `python -m services.cartesia_setup --provision-number` get one). The setup script configures the agent but
   doesn't create it. Set its voice in the Playground too (we use Whitney).
4. Start the Verifier agent (it runs the code webhook on port 8090), or `python -m services.code_webhook`
   to test alone, and expose it: `cloudflared tunnel --url http://localhost:8090`.
5. Put the tunnel URL in `CODE_WEBHOOK_URL` and a random `CODE_WEBHOOK_SECRET` in `.env`, then run
   `python -m services.cartesia_setup`. It prints `CARTESIA_AGENT_ID` and `CARTESIA_FROM_NUMBER_ID` for `.env`.
6. Debug with `python -m services.cartesia_setup --recent-calls` (call transcripts).

## Known limitations

- Cartesia numbers can only call US numbers. That fits our case (students in the US), but we can't call a
  parent abroad.
- The quick cloudflared tunnel gets a new URL each time it starts, so setup has to be rerun after a restart.
- The agent only acts after the student types or speaks. Silence ends the call after 30 seconds.
- The call agent is an LLM. Code-first and one result per case are enforced by our server, but asking the
  1/2 question and sending the right digit rely on the agent's instructions.
- With a fast model, the agent once resent the previous digits after asking for the code again. The
  instructions now tell it to send only digits typed after its latest request, and the retest passed.
- A 4-digit code is short. The server allows one retry, then leaves the case unconfirmed.
- The question is the same for every case ("a message asking for money"). A student who really asked for
  money earlier could press 1 for a different request.
- We haven't measured how many calls the Startup plan can run at the same time.
