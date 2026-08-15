import json
import os
import re
import threading

_HANDLE_RE = re.compile(r"(?<!\w)@([A-Za-z][A-Za-z0-9_]{4,31})(?!\w)")
_LOCK = threading.Lock()


class Contacts:
    def __init__(self, path: str):
        self.path = path
        self._data = {}
        self.reload()

    def reload(self):
        if not os.path.exists(self.path):
            self._data = {}
            return
        with open(self.path, "r") as f:
            raw = json.load(f)
        raw.pop("_comment", None)
        self._data = raw

    def _save(self):
        with _LOCK:
            with open(self.path, "w") as f:
                json.dump(self._data, f, indent=2)

    def other_channel_for(self, email: str):
        entry = self._data.get(email)
        if not entry:
            return None
        for channel in ("telegram", "discord"):
            if entry.get(channel):
                return channel, entry[channel]
        return None

    def learn_telegram_from_text(self, email: str, text: str) -> bool:
        if self.other_channel_for(email):
            return False
        match = _HANDLE_RE.search(text or "")
        if not match:
            return False
        handle = f"@{match.group(1)}"
        with _LOCK:
            self._data.setdefault(email, {})["telegram"] = handle
        self._save()
        return True