import time
from typing import Any, Optional


class SessionMemory:
    """Short-term cache to avoid repeated pipeline runs for same query."""

    def __init__(self, ttl_seconds: int = 300):
        self.store = {}
        self.ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        entry = self.store.get(key)
        if not entry:
            return None
        if time.time() - entry["ts"] > self.ttl:
            del self.store[key]
            return None
        return entry["value"]

    def set(self, key: str, value: Any) -> None:
        self.store[key] = {"value": value, "ts": time.time()}

    def has(self, key: str) -> bool:
        return self.get(key) is not None

    def clear(self) -> None:
        self.store.clear()