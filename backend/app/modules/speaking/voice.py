"""Provider-independent boundary for the real-time AI voice examiner (future LiveKit integration).

Nothing is connected: `provider()` returns None until an adapter calls `register()`, and rooms
then run in *guided* mode (examiner lines from the published configuration, candidate answers
recorded). A live adapter must:

1. `create_session(room)` -> a `VoiceConnection` the browser uses to join (e.g. LiveKit URL and
   participant token) and start the examiner agent with `room.instructions` / `room.plan`.
2. Post transcript and lifecycle events to the internal endpoint
   `POST /api/v1/internal/speaking/rooms/{session_id}/events` (`X-Internal-Token`), handled by
   `rooms.ingest_events` (idempotent on `seq`).
3. `end_session(room_code)` when the candidate ends the room.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class RoomContext:
    session_id: str
    room_code: str
    candidate_id: str
    examiner: dict[str, Any]  # profile snapshot (name, style, voice settings)
    instructions: dict[str, Any]  # structured examiner instructions + conversation rules
    plan: list[dict[str, Any]]  # ordered parts/questions/timing the examiner follows


@dataclass(frozen=True)
class VoiceConnection:
    provider: str
    url: str
    token: str
    expires_at: datetime


@runtime_checkable
class SpeakingVoiceProvider(Protocol):
    name: str

    async def create_session(self, room: RoomContext) -> VoiceConnection: ...

    async def end_session(self, room_code: str) -> None: ...


_provider: SpeakingVoiceProvider | None = None


def register(adapter: SpeakingVoiceProvider | None) -> None:
    global _provider
    _provider = adapter


def provider() -> SpeakingVoiceProvider | None:
    return _provider
