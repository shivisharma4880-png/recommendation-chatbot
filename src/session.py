from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from collections import OrderedDict
from dataclasses import asdict, fields
from pathlib import Path
from typing import Dict

from src.filters import ShopperSlots

SESSION_PATH = Path(__file__).resolve().parent.parent / "data" / "sessions.json"
MAX_SESSIONS = 500
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")
logger = logging.getLogger(__name__)


def valid_session_id(chat_id: str) -> bool:
    return bool(SESSION_ID_RE.match(chat_id or ""))


class SessionStore:
    """Per-chat shopper slots, persisted to a JSON file.

    Thread-safe (the web app runs requests in a thread pool): one lock per chat so a chat's turns
    are processed in order, and one store lock around the dict and the atomic file write.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or SESSION_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: "OrderedDict[str, ShopperSlots]" = OrderedDict()
        self._lock = threading.RLock()
        self._chat_locks: Dict[str, threading.Lock] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read %s; starting with empty sessions", self.path)
            return
        if not isinstance(data, dict):
            return
        valid = {f.name for f in fields(ShopperSlots)}
        for chat_id, payload in data.items():
            if not isinstance(payload, dict):
                continue
            filtered = {k: v for k, v in payload.items() if k in valid}
            try:
                slots = ShopperSlots(**filtered)
                slots.canonicalise()  # sessions written by older versions may hold raw values
                self._cache[str(chat_id)] = slots
            except (TypeError, ValueError, AttributeError):
                continue
        while len(self._cache) > MAX_SESSIONS:
            self._cache.popitem(last=False)

    def _save(self) -> None:
        serializable = {cid: asdict(slots) for cid, slots in self._cache.items()}
        payload = json.dumps(serializable, indent=2, ensure_ascii=False)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=".sessions-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp_name, self.path)  # atomic: a crash never leaves a half-written file
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def chat_lock(self, chat_id: str) -> threading.Lock:
        with self._lock:
            lock = self._chat_locks.get(chat_id)
            if lock is None:
                lock = self._chat_locks[chat_id] = threading.Lock()
            return lock

    def get(self, chat_id: str) -> ShopperSlots:
        with self._lock:
            if chat_id not in self._cache:
                self._cache[chat_id] = ShopperSlots()
                while len(self._cache) > MAX_SESSIONS:
                    old, _ = self._cache.popitem(last=False)
                    self._chat_locks.pop(old, None)
            else:
                self._cache.move_to_end(chat_id)
            return self._cache[chat_id]

    def update(self, chat_id: str, slots: ShopperSlots) -> None:
        with self._lock:
            self._cache[chat_id] = slots
            self._cache.move_to_end(chat_id)
            self._save()

    def reset(self, chat_id: str) -> ShopperSlots:
        with self._lock:
            slots = ShopperSlots()
            self._cache[chat_id] = slots
            self._cache.move_to_end(chat_id)
            self._save()
            return slots
