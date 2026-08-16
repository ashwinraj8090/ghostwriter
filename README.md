# Ghostwriter — Your Inbox's Silent Partner

An AI agent that triages your email, drafts replies in your voice, gets your approval on Telegram, and follows up with silent recipients on a channel they'll actually see.

Built for the **Caspian AI Agent Hackathon**, using [`caspian-sdk`](https://github.com/TryCaspian/caspian-sdk) to give one agent identity across **Email + Telegram**, behind a single message handler.

---

## Table of contents

- [The problem](#the-problem)
- [What Ghostwriter does](#what-ghostwriter-does)
- [Why this is a different use of Caspian](#why-this-is-a-different-use-of-caspian)
- [How this satisfies the hackathon requirements](#how-this-satisfies-the-hackathon-requirements)
- [Architecture](#architecture)
- [Step-by-step: what actually happens](#step-by-step-what-actually-happens)
- [Project structure](#project-structure)
- [Setup](#setup)
- [Running it](#running-it)
- [Optional: deploying so it runs 24/7](#optional-deploying-so-it-runs-247)
- [Honest notes on real-world behavior](#honest-notes-on-real-world-behavior)
- [Demo notes](#demo-notes)
- [Tech stack](#tech-stack)
- [What's next](#whats-next-not-built-yet)
- [License](#license)

---

## The problem

Messages go unanswered — not because people don't care, but because replying takes context-switching and effort. And often the reply is *also* waiting on the other person, sitting unread in an inbox they don't check.

## What Ghostwriter does

1. **Watches an inbox** for incoming email.
2. **Uses AI to triage** each message — ignore it, it needs a reply, or it's urgent — with a visible one-line reason on every card, not just a verdict.
3. **Drafts a reply in your voice** — using examples of your real writing as style reference.
4. **Sends you a card on Telegram** with the draft and three actions: **Send / Edit / Snooze**.
5. **Sends the approved reply** the moment you decide, correctly threaded in the original email conversation.
6. **Follows up on a different channel if the recipient goes quiet.** If you've approved a reply and the recipient doesn't respond, and they've shared a Telegram handle (or the agent learned one from something they wrote), Ghostwriter follows up with *them* on Telegram — instead of waiting on an inbox that isn't working.
7. **Learns contacts dynamically.** Nothing is hardcoded. If a sender mentions a `@handle` in their email, the agent saves it automatically. If it doesn't have one on file, it asks — once, in the very first reply, while it knows the person is actively checking that inbox.
8. **Earns autonomy over time.** The agent tracks Send/Edit/Snooze decisions per sender. Once a sender has a track record of approved-as-is replies, low-stakes follow-ups to them get sent automatically — no approval needed — and the agent only steps back in if something's urgent or unusual.

## Why this is a different use of Caspian

Most multi-channel agents use a second channel to alert the *same* person twice — e.g. "notify me on Slack **and** Telegram." Ghostwriter uses the two channels for two different roles instead:

- **Email is the surface being managed** — where the actual conversation happens.
- **Telegram is the control room** — where the owner approves, edits, or snoozes.
- **Outward reach turns the identity outward** — the agent uses the *same* Caspian identity to reach the *other person*, not just the owner, directly reusing Caspian's core pitch ("one identity, any channel, any human") in a literal way most implementations won't.

---

## How this satisfies the hackathon requirements

| Requirement | How Ghostwriter satisfies it |
|---|---|
| **Use the caspian-sdk** | Every core action goes through `caspian_sdk.CommClient`: `connect_email()`, `connect_telegram()`, `send_message()`, `reply()`, `initiate()`, `on_message`, `on_interaction`. |
| **Run on at least two supported communication channels** | Email and Telegram, both live-tested end to end (Discord is also wired in, optional). |
| **Using a single handler** | One `@client.on_message` function branches by `message.channel` — not separate handlers duplicated per channel. |
| **Solves a real problem** | Universal, everyday pain: replying to email, and following up when people go quiet. |
| **Creativity/originality** | Two channels playing different roles, plus reaching the recipient — not just the owner — with the same agent identity. |
| **Functional implementation** | Every feature has been tested against the real Caspian API, real email delivery, and a real second Telegram device — not mocked. |

---

## Architecture

```
Email inbound ──▶ on_message ──▶ AI triage ──▶ AI draft ──▶ store pending draft
                                                                  │
                                                                  ▼
                                                   push Telegram card to owner
                                                   (Send / Edit / Snooze)
Telegram inbound (owner) ──▶ on_message / on_interaction ──▶ resolve draft ──▶ send via email

Background watcher (runs alongside client.listen()):
  • unanswered too long + sender trusted     → auto-send, notify owner, no approval needed
  • recipient hasn't replied + has a channel → outward nudge via Telegram
```

One `@client.on_message` handler, branching on `message.channel` and sender identity — never duplicated per channel.

---

## Step-by-step: what actually happens

1. An email arrives at the agent's address.
2. The AI reads it and classifies it: `ignore`, `reply`, or `urgent` — plus a one-line reason, shown on every card.
3. If the email mentions a Telegram handle, the agent saves it automatically for future follow-ups (dynamic contact learning — nothing hardcoded).
4. If the sender is already trusted (a track record of approved replies) and it's not urgent, the agent sends the reply immediately and just tells the owner what it did.
5. Otherwise, the AI drafts a reply — in the owner's voice — and if there's no channel on file for this sender yet, adds a short line asking for one.
6. A card is pushed to the owner's Telegram: subject, draft, urgency, the AI's reasoning, and three buttons.
7. The owner taps **Send** (sends as drafted), **Edit** (replaces with their own text), or **Snooze** (does nothing, for now).
8. In the background, a watcher checks periodically: if a reply was sent and the recipient goes quiet past a threshold, and a fallback channel is on file, the agent follows up with them there — and tells the owner it did.

---

## Project structure

```
ghostwriter/
  agent.py        # CommClient wiring, on_message/on_interaction handlers, background watcher
  ai.py            # LLM calls: triage, drafting, escalation/tone detection
  storage.py       # JSON-backed state: pending drafts, trust scores, threads, learned contacts
  contacts.py      # dynamic contact learning + lookup for outward reach
  config.py        # environment configuration
scripts/
  run.py           # entrypoint
demo/
  seed_trust.py       # pre-seeds approval history to demo trust calibration quickly
  sent_examples.txt   # your own past sent emails, used as style reference for drafts
contacts.json.example  # template — real contacts.json is gitignored, never committed
.env.example            # template — real .env is gitignored, never committed
```

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
cp contacts.json.example contacts.json
```

Fill in `.env`:
- `CASPIAN_API_KEY` — from Caspian
- `TELEGRAM_BOT_TOKEN` — create a bot via [@BotFather](https://t.me/BotFather) on Telegram
- `GROQ_API_KEY` — free, no credit card, from [console.groq.com/keys](https://console.groq.com/keys) (default AI provider)
  - Or set `AI_PROVIDER=anthropic` and provide `ANTHROPIC_API_KEY` instead, if preferred

Add a few of your own past sent emails to `demo/sent_examples.txt` so drafts sound like you.

## Running it

```bash
python scripts/run.py
```

Message your Telegram bot once (e.g. "hi") to register yourself as the owner — this is how the agent knows where to send approval cards, since those are proactive messages, not replies to something you sent it. This is a one-time step; it's remembered across restarts.

## Optional: deploying so it runs 24/7

Ghostwriter runs as a long-lived background process (`client.listen()`) — locally, that's a terminal window; in production, this runs the exact same way on a small always-on host, no code changes needed:

1. Push this repo to GitHub (already done if you're reading this there).
2. Create a project on a host that supports background workers (e.g. Railway, Render).
3. Set the start command to `python scripts/run.py`.
4. Add the same variables from your `.env` as environment variables in the host's dashboard — never commit real secrets.
5. Deploy — check the logs for the same startup lines you see locally.

---

## Honest notes on real-world behavior

- **The agent has its own email address** (provisioned by Caspian), not your personal inbox. To route your real mail to it, forward specific messages, or use it as a dedicated address for a workflow. This is standard for how agent identities work — not a shortcut taken for the demo.
- **Outward reach requires the contact to have messaged the bot at least once first** — a real Telegram platform rule (bots can't cold-message someone who's never started a chat with them). The agent works around Caspian's `initiate` capability restriction by reusing an existing conversation once one exists.
- **Not every sender will have a fallback channel on file**, and that's by design — outward reach activates only once a contact has shared one (mentioned directly, or in response to being asked). For everyone else, the agent still triages, drafts, and manages approval normally; it just can't follow up elsewhere for that specific person.
- **This is a human-in-the-loop agent by design** — most actions wait for owner approval, except once a sender has earned trust. This mirrors how serious production agent deployments are usually built: autonomy is earned, not assumed.

---

## Demo notes

- `UNANSWERED_THRESHOLD_SECONDS` is set low during testing/recording to avoid waiting hours for a real demo — this is stated explicitly in the demo video, not hidden.
- `demo/seed_trust.py <email> <count>` pre-seeds approval history so the "the agent now acts on its own" moment is visible in one take.

---

## Tech stack

- [`caspian-sdk`](https://github.com/TryCaspian/caspian-sdk) — multi-channel agent identity (email, Telegram, Discord)
- [Groq](https://groq.com) — free LLM inference (default), or Anthropic Claude as an alternative
- Python, JSON-backed local state (swap for a real DB for production use)

---

## What's next (not built yet)

- WhatsApp/Slack as additional fallback channels (architecture already supports adding them)
- A real database instead of JSON file storage
- Auto-refreshing the in-memory contact list when new contacts are learned mid-run, instead of only at startup

---

## License

MIT — free to use, modify, and build on.
