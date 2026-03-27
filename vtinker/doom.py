"""Doom-loop detector: catches the agent repeating the same failed action."""
from __future__ import annotations

import hashlib


class DoomDetector:
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self._history: list[str] = []

    def record(self, action: str, context: str) -> None:
        h = hashlib.sha256(f"{action}:{context}".encode()).hexdigest()[:16]
        self._history.append(h)

    def is_looping(self) -> bool:
        if len(self._history) < self.threshold:
            return False
        return len(set(self._history[-self.threshold:])) == 1

    def reset(self) -> None:
        self._history.clear()
