"""Recording feature consents (e.g. voice processing and audio recording for Speaking)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import ConsentType, UserConsent
from app.shared.ids import new_id

VOICE_CONSENT_VERSION = "speaking-2026-11"


async def grant_voice_consents(db: AsyncSession, user_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Store the candidate's explicit consents to voice processing and audio recording.
    Returns (processing_consent_id, recording_consent_id)."""
    ids = []
    for consent in (ConsentType.VOICE_PROCESSING, ConsentType.AUDIO_RECORDING):
        row = UserConsent(
            id=new_id(),
            user_id=user_id,
            consent_type=consent.value,
            document_version=VOICE_CONSENT_VERSION,
            granted=True,
        )
        db.add(row)
        ids.append(row.id)
    await db.flush()
    return ids[0], ids[1]
