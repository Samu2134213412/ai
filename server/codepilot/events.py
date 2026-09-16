"""Typed session events and the in-process fan-out hub.

Event names are a closed set so the mobile app and dashboard can switch on them
instead of parsing console text. Every event is persisted with a per-session
sequence number before it is broadcast, which is what makes reconnect-and-replay
lossless: a client reconnects with the last ``seq`` it saw and gets the rest.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import AsyncIterator

from .db import Database

# --- event type constants -------------------------------------------------
SESSION_STARTED = "session.started"
SESSION_COMPLETED = "session.completed"
SESSION_FAILED = "session.failed"
SESSION_CANCELLED = "session.cancelled"
SESSION_STATUS = "session.status"

ASSISTANT_MESSAGE = "assistant.message"
ASSISTANT_THINKING = "assistant.thinking"
USER_MESSAGE = "user.message"

TOOL_STARTED = "tool.started"
TOOL_FINISHED = "tool.finished"
TOOL_APPROVAL_REQUIRED = "tool.approval_required"
TOOL_APPROVAL_RESOLVED = "tool.approval_resolved"

FILE_CHANGED = "file.changed"
TEST_RESULT = "test.result"
ERROR = "session.error"
RAW = "claude.raw"

EVENT_TYPES = {
    SESSION_STARTED, SESSION_COMPLETED, SESSION_FAILED, SESSION_CANCELLED,
    SESSION_STATUS, ASSISTANT_MESSAGE, ASSISTANT_THINKING, USER_MESSAGE,
    TOOL_STARTED, TOOL_FINISHED, TOOL_APPROVAL_REQUIRED, TOOL_APPROVAL_RESOLVED,
    FILE_CHANGED, TEST_RESULT, ERROR, RAW,
}

#: Events that are noisy and only useful for debugging; clients opt in.
VERBOSE_TYPES = {RAW, ASSISTANT_THINKING}

MAX_QUEUE = 1000


class EventHub:
    """Persists events and fans them out to live subscribers."""

    def __init__(self, db: Database):
        self.db = db
        self._subs: dict[str, set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def publish(self, session_id: str, etype: str, payload: dict) -> dict:
        if etype not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {etype}")
        event = self.db.append_event(session_id, etype, payload)
        async with self._lock:
            targets = list(self._subs.get(session_id, ())) + list(self._subs.get("*", ()))
        for queue in targets:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A client too slow to keep up loses live events but can still
                # recover the full log by replaying from its last seq.
                pass
        return event

    @contextlib.asynccontextmanager
    async def subscribe(self, session_id: str) -> AsyncIterator[asyncio.Queue]:
        """Subscribe to one session, or to ``"*"`` for everything."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE)
        async with self._lock:
            self._subs.setdefault(session_id, set()).add(queue)
        try:
            yield queue
        finally:
            async with self._lock:
                subs = self._subs.get(session_id)
                if subs:
                    subs.discard(queue)
                    if not subs:
                        del self._subs[session_id]

    def replay(self, session_id: str, after_seq: int = 0) -> list[dict]:
        return self.db.get_events(session_id, after_seq)

    def subscriber_count(self, session_id: str) -> int:
        return len(self._subs.get(session_id, ()))
