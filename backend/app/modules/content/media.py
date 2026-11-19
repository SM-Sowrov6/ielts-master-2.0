"""Content media uploads (docs/CONTENT_MANAGEMENT_ARCHITECTURE.md §5), verified subset.

1. `create_upload`: the server checks kind, MIME type allow-list and declared size, creates a
   `media_assets` row (`uploading`) and returns a 5-minute presigned PUT URL. The browser uploads
   straight to object storage (no binary data passes through the API or PostgreSQL).
2. `complete_upload`: the server reads the stored object back and checks that it exists, that
   its size matches the declaration and the limit, that its leading bytes match the declared
   format (file signature) and that its SHA-256 matches. Only then is the asset `ready`;
   otherwise it is `failed` and the object is deleted.

Not implemented yet (Phase 5b media worker): malware scanning, transcoding, duration extraction.
Because of that, uploads are refused outside local/ci (`Settings.media_uploads_open`).
Assets are immutable: replacing a section's audio means uploading a new asset.
"""

import contextlib
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.storage import ObjectStorage, StorageUnavailableError
from app.modules.audit import api as audit
from app.modules.content.enums import AssetKind, AssetStatus
from app.modules.content.errors import (
    ContentNotFoundError,
    MediaRejectedError,
    MediaStateError,
    MediaStorageUnavailableError,
    MediaUploadsDisabledError,
)
from app.modules.content.models import MediaAsset
from app.modules.content.service import licence_for_test
from app.shared.ids import new_id


def _mp3(head: bytes) -> bool:
    return head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0)


def _wav(head: bytes) -> bool:
    return head[:4] == b"RIFF" and head[8:12] == b"WAVE"


def _m4a(head: bytes) -> bool:
    return head[4:8] == b"ftyp"


def _png(head: bytes) -> bool:
    return head.startswith(b"\x89PNG\r\n\x1a\n")


def _jpeg(head: bytes) -> bool:
    return head.startswith(b"\xff\xd8\xff")


def _webp(head: bytes) -> bool:
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


@dataclass(frozen=True)
class _Format:
    extension: str
    matches: Callable[[bytes], bool]


ALLOWED: dict[str, dict[str, _Format]] = {
    AssetKind.AUDIO: {
        "audio/mpeg": _Format(".mp3", _mp3),
        "audio/wav": _Format(".wav", _wav),
        "audio/x-wav": _Format(".wav", _wav),
        "audio/wave": _Format(".wav", _wav),
        "audio/mp4": _Format(".m4a", _m4a),
        "audio/x-m4a": _Format(".m4a", _m4a),
    },
    AssetKind.IMAGE: {
        "image/png": _Format(".png", _png),
        "image/jpeg": _Format(".jpg", _jpeg),
        "image/webp": _Format(".webp", _webp),
    },
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def max_bytes(settings: Settings, kind: str) -> int:
    return (
        settings.media_max_audio_bytes
        if kind == AssetKind.AUDIO
        else settings.media_max_image_bytes
    )


def storage_for(settings: Settings) -> ObjectStorage:
    if not settings.media_uploads_open:
        if not settings.media_storage_configured:
            raise MediaStorageUnavailableError("Object storage is not configured.")
        raise MediaUploadsDisabledError()
    try:
        return ObjectStorage(settings)
    except StorageUnavailableError as exc:
        raise MediaStorageUnavailableError(str(exc)) from exc


def playback_storage(settings: Settings) -> ObjectStorage:
    """Reading already-verified assets works whenever storage is configured."""
    try:
        return ObjectStorage(settings)
    except StorageUnavailableError as exc:
        raise MediaStorageUnavailableError(str(exc)) from exc


@dataclass(frozen=True)
class UploadTicket:
    asset: MediaAsset
    upload_url: str
    headers: dict[str, str]


async def create_upload(
    session: AsyncSession,
    storage: ObjectStorage,
    settings: Settings,
    *,
    test_id: uuid.UUID,
    kind: str,
    filename: str,
    mime_type: str,
    size_bytes: int,
    sha256: str,
    actor_id: uuid.UUID,
) -> UploadTicket:
    formats = ALLOWED.get(kind)
    if formats is None:
        raise MediaRejectedError(f"Uploads of kind {kind!r} are not supported.")
    fmt = formats.get(mime_type.lower())
    if fmt is None:
        allowed = ", ".join(sorted({f.extension for f in formats.values()}))
        raise MediaRejectedError(f"Unsupported file type. Allowed: {allowed}.")
    limit = max_bytes(settings, kind)
    if size_bytes <= 0 or size_bytes > limit:
        raise MediaRejectedError(f"Files must be between 1 byte and {limit // (1024 * 1024)} MB.")
    if not _SHA256.match(sha256):
        raise MediaRejectedError("A SHA-256 checksum (64 lowercase hex characters) is required.")
    licence = await licence_for_test(session, test_id)
    if licence is None:
        raise ContentNotFoundError(f"Test {test_id} not found.")
    asset_id = new_id()
    asset = MediaAsset(
        id=asset_id,
        kind=kind,
        storage_key=f"uploads/{kind}/{asset_id}{fmt.extension}",
        mime_type=mime_type.lower(),
        size_bytes=size_bytes,
        checksum_sha256=sha256,
        status=AssetStatus.UPLOADING.value,
        license_id=licence.id,
        original_filename=filename[:255],
        uploaded_by=actor_id,
    )
    session.add(asset)
    await session.flush()
    try:
        await storage.ensure_bucket()
        url = await storage.presign_put(asset.storage_key, asset.mime_type)
    except StorageUnavailableError as exc:
        raise MediaStorageUnavailableError(str(exc)) from exc
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.media.upload_started",
        entity_type="media_asset",
        entity_id=asset.id,
        changes={"kind": kind, "mime_type": asset.mime_type, "size_bytes": size_bytes},
    )
    return UploadTicket(asset, url, {"Content-Type": asset.mime_type})


async def complete_upload(
    session: AsyncSession,
    storage: ObjectStorage,
    settings: Settings,
    *,
    asset_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> tuple[MediaAsset, str | None]:
    """Returns (asset, rejection message). A rejection is persisted (`failed` + audit) and must be
    committed by the caller before it reports the error, so it is returned rather than raised."""
    asset = await session.get(MediaAsset, asset_id, with_for_update=True)
    if asset is None:
        raise ContentNotFoundError(f"Media asset {asset_id} not found.")
    if asset.status == AssetStatus.READY:
        return asset, None  # idempotent
    if asset.status != AssetStatus.UPLOADING:
        raise MediaStateError(f"The asset is {asset.status}.")
    limit = max_bytes(settings, asset.kind)
    try:
        info = await storage.inspect(asset.storage_key, max_bytes=limit)
    except StorageUnavailableError as exc:
        raise MediaStorageUnavailableError(str(exc)) from exc
    if info is None:
        raise MediaStateError("The file has not been uploaded to storage yet.")
    fmt = ALLOWED[asset.kind][asset.mime_type]
    reason = None
    if info.size_bytes != asset.size_bytes or info.size_bytes > limit:
        reason = "size_mismatch"
    elif not fmt.matches(info.head):
        reason = "signature_mismatch"
    elif info.sha256 != asset.checksum_sha256:
        reason = "checksum_mismatch"
    if reason is not None:
        asset.status = AssetStatus.FAILED.value
        # The row is failed either way; an orphan object left behind is private and harmless.
        with contextlib.suppress(StorageUnavailableError):
            await storage.delete(asset.storage_key)
        await audit.record(
            session,
            actor_id=actor_id,
            action="content.media.rejected",
            entity_type="media_asset",
            entity_id=asset.id,
            changes={"reason": reason},
        )
        await session.flush()
        messages = {
            "size_mismatch": "The stored file's size does not match the declared size.",
            "signature_mismatch": "The file's content does not match its declared type.",
            "checksum_mismatch": "The stored file's checksum does not match.",
        }
        return asset, messages[reason]
    asset.status = AssetStatus.READY.value
    await audit.record(
        session,
        actor_id=actor_id,
        action="content.media.uploaded",
        entity_type="media_asset",
        entity_id=asset.id,
        changes={"kind": asset.kind, "size_bytes": asset.size_bytes},
    )
    await session.flush()
    return asset, None


async def playback_url(
    session: AsyncSession, storage: ObjectStorage, *, asset_id: uuid.UUID
) -> tuple[MediaAsset, str]:
    """Short-lived URL for an admin to play/view a ready asset."""
    asset = await session.get(MediaAsset, asset_id)
    if asset is None:
        raise ContentNotFoundError(f"Media asset {asset_id} not found.")
    if asset.status != AssetStatus.READY:
        raise MediaStateError(f"The asset is {asset.status}.")
    try:
        return asset, await storage.presign_get(asset.storage_key, asset.mime_type)
    except StorageUnavailableError as exc:
        raise MediaStorageUnavailableError(str(exc)) from exc
