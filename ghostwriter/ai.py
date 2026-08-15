"""
The 'brain' of Ghostwriter. Caspian moves the messages; everything here is
the judgment layer: deciding what matters, writing like the owner, and
reading a thread's tone over time.
"""
import json
import os

from .config import config

_client = None


def _get_client():
    """Lazily builds whichever provider's client is configured.
    Groq is the default because it's free (no credit card needed) --
    set AI_PROVIDER=anthropic in .env to use Claude instead."""
    global _client
    if _client is None:
        if config.AI_PROVIDER == "anthropic":
            import anthropic

            _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        else:
            import groq

            _client = groq.Groq(api_key=config.GROQ_API_KEY)
    return _client


def _call(system: str, user: str, max_tokens: int = 600) -> str:
    client = _get_client()
    if config.AI_PROVIDER == "anthropic":
        resp = client.messages.create(
            model=config.AI_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if block.type == "text").strip()
    else:
        resp = client.chat.completions.create(
            model=config.GROQ_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content.strip()


def _load_style_examples() -> str:
    path = config.SENT_EXAMPLES_FILE
    if not os.path.exists(path):
        return ""
    with open(path, "r") as f:
        text = f.read().strip()
    return text[:4000]  # keep the prompt small


# ---------------------------------------------------------------------------
# 1. Triage: does this even need a human decision?
# ---------------------------------------------------------------------------
TRIAGE_SYSTEM = """You triage inbound email for someone who gets too much of it.
Classify the message into exactly one category:
- "ignore": informational only, no reply needed (newsletters, FYI, receipts, auto-notifications)
- "reply": needs a reply but isn't time-sensitive
- "urgent": needs a reply soon (a deadline, a blocking question, someone waiting on this
  person specifically, escalating frustration, money/legal/contract stakes)

Respond with ONLY compact JSON: {"category": "...", "reason": "one short sentence"}
No markdown, no preamble."""


def triage(subject: str, body: str, sender: str) -> dict:
    user = f"From: {sender}\nSubject: {subject}\n\n{body}"
    raw = _call(TRIAGE_SYSTEM, user, max_tokens=200)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fail safe: if the model didn't return clean JSON, treat as needing
        # a human look rather than silently dropping it.
        return {"category": "reply", "reason": "triage parse failed, defaulting to reply"}


# ---------------------------------------------------------------------------
# 2. Draft a reply in the owner's voice
# ---------------------------------------------------------------------------
def draft_reply(subject: str, body: str, sender: str, thread_history: list) -> str:
    style = _load_style_examples()
    style_block = (
        f"Here are examples of how this person writes email, to match tone and length:\n---\n{style}\n---\n\n"
        if style
        else ""
    )
    history_block = ""
    if thread_history:
        lines = [f"{h['role']}: {h['text']}" for h in thread_history[-6:]]
        history_block = "Prior messages in this thread:\n" + "\n".join(lines) + "\n\n"

    system = (
        "You draft email replies on behalf of a busy person, in their voice. "
        "Be concise, natural, and match the tone/formality of the style examples if given. "
        "Do not invent commitments, prices, or facts not present in the thread. "
        "If information is missing, write a reply that asks for it rather than guessing. "
        "Output ONLY the reply body text, no subject line, no signature block, no preamble."
    )
    user = f"{style_block}{history_block}Reply to this email:\nFrom: {sender}\nSubject: {subject}\n\n{body}"
    return _call(system, user, max_tokens=500)


# ---------------------------------------------------------------------------
# 3. Escalation / tone detection across a thread
# ---------------------------------------------------------------------------
ESCALATION_SYSTEM = """You read a back-and-forth email thread and judge whether the
other person's tone or urgency is escalating (getting impatient, repeating a request,
turning terse or frustrated) or stable/de-escalating.

Respond with ONLY compact JSON:
{"escalated": true|false, "note": "one short sentence explaining why"}"""


def detect_escalation(thread_history: list) -> dict:
    if len(thread_history) < 2:
        return {"escalated": False, "note": "not enough history yet"}
    lines = [f"{h['role']}: {h['text']}" for h in thread_history[-10:]]
    raw = _call(ESCALATION_SYSTEM, "\n".join(lines), max_tokens=150)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"escalated": False, "note": "escalation parse failed"}
