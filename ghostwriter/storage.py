import json
import os
import threading
import time
import uuid

_LOCK = threading.Lock()


class Storage:
    def __init__(self, path: str):
        self.path = path
        if not os.path.exists(self.path):
            self._write(
                {
                    "owner": {},
                    "pending_drafts": {},
                    "threads": {},
                    "trust": {},
                    "awaiting_edit": {},
                }
            )

    def _read(self) -> dict:
        with open(self.path, "r") as f:
            return json.load(f)

    def _write(self, data: dict):
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def remember_contact_conversation(self, channel, handle, conversation_id):
        with _LOCK:
            data = self._read()
            data.setdefault("contact_conversations", {})
            key = f"{channel}:{handle.lstrip('@').lower()}"
            data["contact_conversations"][key] = conversation_id
            self._write(data)

    def get_contact_conversation(self, channel, handle):
        with _LOCK:
            data = self._read()
        key = f"{channel}:{handle.lstrip('@').lower()}"
        return data.get("contact_conversations", {}).get(key)

    def set_owner_telegram(self, sender: str, conversation_id: str):
        with _LOCK:
            data = self._read()
            data["owner"]["telegram_sender"] = sender
            data["owner"]["telegram_conversation_id"] = conversation_id
            self._write(data)

    def get_owner_telegram_sender(self):
        with _LOCK:
            return self._read()["owner"].get("telegram_sender")

    def get_owner_telegram_conversation(self):
        with _LOCK:
            return self._read()["owner"].get("telegram_conversation_id")

    def add_pending_draft(self, conversation_id, sender, subject, original_text, draft_text, urgency="normal", message_id=None):
        draft_id = uuid.uuid4().hex[:8]
        with _LOCK:
            data = self._read()
            data["pending_drafts"][draft_id] = {
                "id": draft_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "sender": sender,
                "subject": subject,
                "original_text": original_text,
                "draft_text": draft_text,
                "urgency": urgency,
                "created_at": time.time(),
                "status": "pending",
            }
            self._write(data)
        return draft_id

    def get_draft(self, draft_id):
        with _LOCK:
            return self._read()["pending_drafts"].get(draft_id)

    def update_draft(self, draft_id, **fields):
        with _LOCK:
            data = self._read()
            if draft_id in data["pending_drafts"]:
                data["pending_drafts"][draft_id].update(fields)
                self._write(data)

    def latest_pending_draft_for_owner(self):
        with _LOCK:
            data = self._read()
        pending = [d for d in data["pending_drafts"].values() if d["status"] == "pending"]
        if not pending:
            return None
        return max(pending, key=lambda d: d["created_at"])

    def touch_thread(self, conversation_id, sender, subject):
        with _LOCK:
            data = self._read()
            t = data["threads"].setdefault(
                conversation_id,
                {
                    "sender": sender,
                    "subject": subject,
                    "history": [],
                    "last_inbound_at": time.time(),
                    "recipient_replied": True,
                    "outward_nudged": False,
                },
            )
            t["last_inbound_at"] = time.time()
            t["recipient_replied"] = True
            self._write(data)

    def append_history(self, conversation_id, role, text):
        with _LOCK:
            data = self._read()
            t = data["threads"].get(conversation_id)
            if t:
                t["history"].append({"role": role, "text": text, "at": time.time()})
                self._write(data)

    def mark_agent_sent(self, conversation_id):
        with _LOCK:
            data = self._read()
            t = data["threads"].get(conversation_id)
            if t:
                t["last_sent_at"] = time.time()
                t["recipient_replied"] = False
                self._write(data)

    def mark_outward_nudged(self, conversation_id):
        with _LOCK:
            data = self._read()
            t = data["threads"].get(conversation_id)
            if t:
                t["outward_nudged"] = True
                self._write(data)

    def all_threads(self):
        with _LOCK:
            return dict(self._read()["threads"])

    def record_decision(self, sender, decision):
        with _LOCK:
            data = self._read()
            t = data["trust"].setdefault(sender, {"approved": 0, "edited": 0, "rejected": 0})
            t[decision] = t.get(decision, 0) + 1
            self._write(data)

    def trust_score(self, sender):
        with _LOCK:
            data = self._read()
        return data["trust"].get(sender, {"approved": 0, "edited": 0, "rejected": 0})

    def is_trusted(self, sender, threshold):
        score = self.trust_score(sender)
        return score.get("approved", 0) >= threshold

    def set_awaiting_edit(self, chat_id, draft_id):
        with _LOCK:
            data = self._read()
            data["awaiting_edit"][chat_id] = draft_id
            self._write(data)

    def pop_awaiting_edit(self, chat_id):
        with _LOCK:
            data = self._read()
            draft_id = data["awaiting_edit"].pop(chat_id, None)
            self._write(data)
        return draft_id