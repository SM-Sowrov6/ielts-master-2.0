"""LiveKit implementation of `SpeakingVoiceProvider` (registered when LIVEKIT_* settings exist).

`create_session` creates the LiveKit room, dispatches the examiner agent (voice-engine,
`AGENT_NAME`) with the room context as job metadata, and returns a short-lived participant token
for the candidate's browser. The agent posts transcript/lifecycle events back to
`POST /api/v1/internal/speaking/rooms/{id}/events`. Credentials never leave the server.
"""

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from livekit import api

from app.core.config import Settings
from app.modules.speaking.voice import RoomContext, VoiceConnection

AGENT_NAME = "ielts-examiner"
TOKEN_TTL = timedelta(minutes=30)


def configured(settings: Settings) -> bool:
    return bool(settings.livekit_url and settings.livekit_api_key and settings.livekit_api_secret)


def _http_url(url: str) -> str:
    return url.replace("wss://", "https://", 1).replace("ws://", "http://", 1)


class LiveKitVoice:
    name = "livekit"

    def __init__(self, settings: Settings) -> None:
        if not configured(settings) or settings.livekit_api_secret is None:
            raise ValueError("LiveKit is not configured.")
        self._url = str(settings.livekit_url)
        self._key = str(settings.livekit_api_key)
        self._secret = settings.livekit_api_secret.get_secret_value()

    def _client(self) -> api.LiveKitAPI:
        return api.LiveKitAPI(_http_url(self._url), self._key, self._secret)

    def candidate_token(self, room_code: str, candidate_id: str) -> VoiceConnection:
        expires = datetime.now(UTC) + TOKEN_TTL
        token = (
            api.AccessToken(self._key, self._secret)
            .with_identity(f"candidate-{candidate_id}")
            .with_name("Candidate")
            .with_ttl(TOKEN_TTL)
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_code,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=False,
                )
            )
            .to_jwt()
        )
        return VoiceConnection(provider=self.name, url=self._url, token=token, expires_at=expires)

    async def create_session(self, room: RoomContext) -> VoiceConnection:
        lk = self._client()
        try:
            await lk.room.create_room(
                api.CreateRoomRequest(name=room.room_code, empty_timeout=300, max_participants=3)
            )
            await lk.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name=AGENT_NAME, room=room.room_code, metadata=json.dumps(asdict(room))
                )
            )
        finally:
            await lk.aclose()
        return self.candidate_token(room.room_code, room.candidate_id)

    async def end_session(self, room_code: str) -> None:
        lk = self._client()
        try:
            await lk.room.delete_room(api.DeleteRoomRequest(room=room_code))
        except api.TwirpError:
            pass  # already gone
        finally:
            await lk.aclose()
