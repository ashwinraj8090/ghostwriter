import threading
import time

from caspian_sdk import CommClient, blocks as b

from .ai import detect_escalation, draft_reply, triage
from .config import config
from .contacts import Contacts
from .storage import Storage

storage = Storage(config.STATE_FILE)
contacts = Contacts(config.CONTACTS_FILE)

_connections: dict = {}
_reverse_contacts: dict = {}


def _build_reverse_contacts():
    _reverse_contacts.clear()
    for email, entry in contacts._data.items():
        for channel in ("telegram", "discord"):
            handle = entry.get(channel)
            if handle:
                _reverse_contacts[handle.lstrip("@").lower()] = email


def _urgency_label(category: str) -> str:
    return {"urgent": "🔴 Urgent", "reply": "🟡 Needs a reply", "ignore": "⚪ FYI"}.get(category, category)


def _push_owner_card(client, draft_id: str, sender: str, subject: str, draft_text: str, urgency: str, insight: str = ""):
    owner_conv = storage.get_owner_telegram_conversation()
    if not owner_conv:
        print("[ghostwriter] No owner Telegram conversation yet -- message the Telegram bot once first.")
        return
    text_block = draft_text if len(draft_text) < 900 else draft_text[:900] + "…"
    subtitle = f"{_urgency_label(urgency)} · from {sender}"
    card_text = f"Subject: {subject}\n\n{text_block}"
    if insight:
        card_text += f"\n\n🧠 {insight}"
    try:
        client.send_message(
            owner_conv,
            blocks=[
                b.card(
                    title="Draft reply ready",
                    subtitle=subtitle,
                    text=card_text,
                    buttons=[
                        {"label": "✅ Send", "value": f"gw:send:{draft_id}"},
                        {"label": "✏️ Edit", "value": f"gw:edit:{draft_id}"},
                        {"label": "💤 Snooze", "value": f"gw:snooze:{draft_id}"},
                    ],
                )
            ],
        )
    except Exception as e:
        print(f"[ghostwriter] Failed to push Telegram card: {e}")


def _notify_owner_text(client, text: str):
    owner_conv = storage.get_owner_telegram_conversation()
    if not owner_conv:
        return
    try:
        client.send_message(owner_conv, text=text)
    except Exception as e:
        print(f"[ghostwriter] Failed to notify owner: {e}")


def _extract_email(sender):
    if isinstance(sender, dict):
        return sender.get("address") or sender.get("name") or str(sender)
    return sender


def _handle_email(client, message):
    sender = _extract_email(message.sender)
    subject = message.subject or "(no subject)"
    body = message.text or ""
    conversation_id = message.conversation_id

    storage.touch_thread(conversation_id, sender, subject)
    storage.append_history(conversation_id, "them", body)
    contacts.learn_telegram_from_text(sender, body)

    result = triage(subject, body, sender)
    category = result.get("category", "reply")
    triage_reason = result.get("reason", "")
    print(f"[ghostwriter] triage({sender}) -> {category}: {triage_reason}")

    if category == "ignore":
        return

    thread_history = storage.all_threads().get(conversation_id, {}).get("history", [])
    draft_text = draft_reply(subject, body, sender, thread_history)

    if not contacts.other_channel_for(sender):
        draft_text += (
            "\n\n(By the way, if this thread ever goes quiet, feel free to "
            "share a Telegram handle -- easier for me to follow up there.)"
        )

    escalation = detect_escalation(thread_history)
    insight = triage_reason
    if escalation.get("escalated"):
        insight = f"{triage_reason} · {escalation.get('note', '')}"

    if category != "urgent" and storage.is_trusted(sender, config.TRUST_AUTO_SEND_THRESHOLD):
        message.reply(draft_text)
        storage.append_history(conversation_id, "agent", draft_text)
        storage.mark_agent_sent(conversation_id)
        _notify_owner_text(
            client,
            f"🤖 Auto-sent a reply to {sender} (trusted sender, "
            f"{storage.trust_score(sender)['approved']} approved replies so far):\n\n{draft_text[:400]}",
        )
        print(f"[ghostwriter] auto-sent to trusted sender {sender}")
        return

    draft_id = storage.add_pending_draft(
        conversation_id, sender, subject, body, draft_text, urgency=category, message_id=message.id
    )
    _push_owner_card(client, draft_id, sender, subject, draft_text, category, insight)


def _resolve_action(client, action, draft_id, owner_sender):
    draft = storage.get_draft(draft_id) if draft_id else None
    if not draft:
        return "That draft isn't available anymore."

    if action == "send":
        client.reply(draft["message_id"], text=draft["draft_text"])
        storage.update_draft(draft_id, status="sent")
        storage.append_history(draft["conversation_id"], "agent", draft["draft_text"])
        storage.mark_agent_sent(draft["conversation_id"])
        storage.record_decision(draft["sender"], "approved")
        return "Sent ✅"

    if action == "edit":
        storage.set_awaiting_edit(owner_sender, draft_id)
        return "Send me the replacement text and I'll send that instead."

    if action == "snooze":
        storage.update_draft(draft_id, status="snoozed")
        return "Snoozed -- I'll leave it be for now."

    return "Unknown action."


def _handle_telegram(client, message):
    sender = _extract_email(message.sender)
    text = (message.text or "").strip()

    storage.remember_contact_conversation("telegram", str(sender), message.conversation_id)

    owner_sender = storage.get_owner_telegram_sender()

    if owner_sender is None:
        storage.set_owner_telegram(sender, message.conversation_id)
        message.reply("Registered! I'll ping you here when an email needs a decision (Send / Edit / Snooze).")
        return

    if sender == owner_sender:
        draft_id = storage.pop_awaiting_edit(sender)
        if draft_id:
            draft = storage.get_draft(draft_id)
            if draft:
                client.reply(draft["message_id"], text=text)
                storage.update_draft(draft_id, status="edited", draft_text=text)
                storage.append_history(draft["conversation_id"], "agent", text)
                storage.mark_agent_sent(draft["conversation_id"])
                storage.record_decision(draft["sender"], "edited")
                message.reply("Sent your edited version ✅")
            else:
                message.reply("That draft expired -- it'll come back if it's still relevant.")
            return

        lowered = text.lower()
        if lowered in ("send", "edit", "snooze"):
            latest = storage.latest_pending_draft_for_owner()
            if latest:
                message.reply(_resolve_action(client, lowered, latest["id"], sender))
                return

        message.reply("Hey! I'll ping you here when an email needs a decision.")
        return

    handle_key = str(sender).lstrip("@").lower()
    if handle_key in _reverse_contacts:
        email = _reverse_contacts[handle_key]
        for conv_id, thread in storage.all_threads().items():
            if thread["sender"] == email:
                storage.touch_thread(conv_id, email, thread["subject"])
        message.reply("Thanks -- I'll pass this along.")
        _notify_owner_text(client, f"💬 {email} replied on Telegram instead of email: \"{text}\"")
        return

    message.reply("This bot is wired to one owner right now.")


def _handle_interaction(client, interaction):
    value = interaction.value or ""
    if not value.startswith("gw:"):
        return
    _, action, draft_id = (value.split(":", 2) + [None, None])[:3]
    reply_text = _resolve_action(client, action, draft_id, _extract_email(interaction.sender))
    client.send_message(interaction.conversation_id, text=reply_text)


def _handle_discord(client, message):
    handle_key = str(_extract_email(message.sender)).lstrip("@").lower()
    if handle_key in _reverse_contacts:
        email = _reverse_contacts[handle_key]
        message.reply("Thanks -- I'll pass this along.")
        _notify_owner_text(client, f"💬 {email} replied on Discord instead of email: \"{message.text}\"")
    else:
        message.reply("This bot only relays follow-ups for known contacts right now.")


def _watch_loop(client, stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            for conv_id, thread in storage.all_threads().items():
                if thread.get("recipient_replied", True):
                    continue
                if thread.get("outward_nudged"):
                    continue
                last_sent = thread.get("last_sent_at")
                if not last_sent or (time.time() - last_sent) < config.UNANSWERED_THRESHOLD_SECONDS:
                    continue
                fallback = contacts.other_channel_for(thread["sender"])
                if not fallback:
                    continue
                channel, handle = fallback
                conn = _connections.get(channel)
                if not conn:
                    continue
                nudge = (
                    f"Hey, just following up on the email about \"{thread['subject']}\" -- "
                    f"wanted to make sure it didn't get buried."
                )
                try:
                    existing_conv = storage.get_contact_conversation(channel, handle)
                    if existing_conv:
                        client.send_message(existing_conv, text=nudge)
                    else:
                        client.initiate(conn["id"], handle, text=nudge)
                    storage.mark_outward_nudged(conv_id)
                    _notify_owner_text(
                        client, f"↪️ {thread['sender']} hadn't replied, so I followed up on {channel} instead."
                    )
                    print(f"[ghostwriter] outward nudge sent to {thread['sender']} via {channel}")
                except Exception as e:
                    print(f"[ghostwriter] outward nudge failed: {e}")
        except Exception as e:
            print(f"[ghostwriter] watcher error: {e}")
        stop_event.wait(config.WATCH_INTERVAL_SECONDS)


def run():
    config.validate()
    _build_reverse_contacts()

    client = CommClient()

    email_conn = client.connect_email(username=config.CASPIAN_EMAIL_USERNAME)
    print(f"[ghostwriter] Agent email: {email_conn.get('address')}")
    _connections["email"] = email_conn

    telegram_conn = client.connect_telegram(bot_token=config.TELEGRAM_BOT_TOKEN)
    print(f"[ghostwriter] Telegram bot: {telegram_conn.get('address')}")
    _connections["telegram"] = telegram_conn

    import os

    discord_token = os.getenv("DISCORD_BOT_TOKEN")
    if discord_token:
        try:
            discord_conn = client.connect_discord(bot_token=discord_token)
            print("[ghostwriter] Discord bot connected")
            _connections["discord"] = discord_conn
        except Exception as e:
            print(f"[ghostwriter] Discord not connected: {e}")

    agent_email = email_conn.get("address")

    @client.on_message
    def handle(message):
        if agent_email and _extract_email(message.sender) == agent_email:
            return
        try:
            if message.channel == "email":
                _handle_email(client, message)
            elif message.channel == "telegram":
                _handle_telegram(client, message)
            elif message.channel == "discord":
                _handle_discord(client, message)
            else:
                message.reply("This channel isn't wired up in this build yet.")
        except Exception as e:
            print(f"[ghostwriter] handler error on {message.channel}: {e}")

    @client.on_interaction
    def handle_interaction(interaction):
        try:
            _handle_interaction(client, interaction)
        except Exception as e:
            print(f"[ghostwriter] interaction error: {e}")

    stop_event = threading.Event()
    watcher = threading.Thread(target=_watch_loop, args=(client, stop_event), daemon=True)
    watcher.start()

    print("[ghostwriter] listening...")
    client.listen()