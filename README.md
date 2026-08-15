# Ghostwriter

An AI agent that triages your unanswered email, drafts replies in your voice,
lets you approve them from Telegram, chases silent recipients on a second
channel, and gradually earns the right to send low-stakes replies on its own.

Built for the Caspian AI Agent Hackathon. Uses `caspian-sdk` with a single
`on_message` handler running across **Email + Telegram** (core), with optional
**Discord** used for the outward-reach feature.

## Why this exists

Messages go unanswered not because people don't care, but because replying
takes context-switching and effort — and often the reply is *also* waiting on
the other person, sitting unread in an inbox they don't check.

## What it does

1. **Watches your email** for messages that need a reply.
2. **Triages** each one with an LLM: ignore / needs a reply / urgent. This is
   a judgment call, not a keyword filter.
3. **Drafts a reply in your voice** (few-shot from example sent messages you
   provide).
4. **Pings you on Telegram** with the draft and three actions: `Send`,
   `Edit`, `Snooze`. Telegram is the control room; email is the surface being
   managed — not a duplicate alert.
5. **Sends from email** the moment you approve, in the same thread.
6. **Outward reach**: if the recipient doesn't reply within a configurable
   window, and you've told the agent their Discord/Telegram handle, it
   follows up *on that channel* instead of just waiting on email. This uses
   Caspian's core promise — one identity, any human, any channel — pointed at
   the other party, not just at you.
7. **Trust calibration**: the agent tracks your Send / Edit / Snooze decisions
   per sender. Once a sender has enough approved-as-is replies, low-stakes
   follow-ups to that sender get sent automatically, and the agent only pings
   you again when it's uncertain or the stakes go up.

## Architecture

```
Email inbound ──▶ on_message ──▶ triage (LLM) ──▶ draft (LLM) ──▶ store pending
                                                                    │
                                                                    ▼
                                                     push Telegram card to owner
                                                     (Send / Edit / Snooze)
Telegram inbound (owner) ──▶ on_message ──▶ resolve pending draft ──▶ send via email

Background watcher (runs alongside client.listen):
  - unanswered too long + sender trusted  ──▶ auto-send, log it, no ping
  - unanswered too long + not trusted     ──▶ ping owner on Telegram
  - recipient never replied + has a 2nd channel handle ──▶ outward nudge via client.initiate
```

One `on_message` handler, branching on `message.channel` and `message.sender`
— never duplicated per channel, per the hackathon rules.

## Project layout

```
ghostwriter/
  agent.py        # CommClient wiring + the on_message handler + background watcher
  ai.py            # LLM calls: triage, draft, escalation/tone detection
  storage.py       # tiny JSON-file state store (pending drafts, trust, contacts, threads)
  contacts.py      # email -> other-channel handle lookup
  config.py        # env var loading
scripts/
  run.py           # entrypoint
demo/
  seed_trust.py    # pre-seeds approval history so the "autonomy" moment is visible live
  sent_examples.txt  # paste a few of your own past sent emails here for style few-shot
contacts.json       # you fill this in: {"someone@example.com": {"telegram": "@handle"}}
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# fill in .env: CASPIAN_API_KEY, ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN (from @BotFather)
python scripts/run.py
```

On first run the agent connects email + Telegram, prints the agent's email
address, and starts listening. Message the Telegram bot once from your own
account so it learns your chat id (it says so on first contact) — that's how
it knows where to send proactive pings, since those aren't replies to an
inbound message.

Add a few of your own past sent emails to `demo/sent_examples.txt` (one per
line, or separated by `---`) so drafts sound like you instead of generic.

Fill in `contacts.json` with any recipients whose Discord/Telegram handle you
want the agent able to fall back to.

## Demo notes (be upfront about these in the video)

- **Outward reach**: waiting hours for a real non-reply kills demo pacing.
  Set `UNANSWERED_THRESHOLD_SECONDS` low (e.g. `20`) for the recording and
  say so on camera — the mechanism is real, only the wait is compressed.
- **Trust calibration**: run `python demo/seed_trust.py <sender-email> 5`
  before recording to pre-seed approval history, so you can show the
  before/after (agent asks permission → agent sends on its own) in one take
  instead of doing it live five times.
- Keep the demo to email + Telegram for the core loop (both free, instant,
  no sign-in) and only bring in Discord for the outward-reach beat.

## Hackathon checklist

- [x] Uses `caspian-sdk`
- [x] Runs on 2+ channels (Email, Telegram, optionally Discord) behind one
      `on_message` handler — no per-channel handler duplication
- [x] Solves a real, everyday problem
- [x] AI does judgment work (triage, tone/escalation reasoning, confidence-
      gated autonomy), not just text generation

## Notes on the SDK calls

This was built against the current `caspian-sdk` docs/SKILL guide. A couple
of calls (`client.initiate(...)` for proactive Telegram/Discord messages, the
exact shape of button-callback delivery) are used based on the documented
patterns — double-check method names/signatures against
`https://www.trycaspianai.com/docs/` and the SDK reference if they've moved,
since the SDK is actively developed. Everything is isolated in `agent.py` and
`ai.py` so it's easy to patch.
