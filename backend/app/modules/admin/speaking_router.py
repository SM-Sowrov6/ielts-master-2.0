"""Admin AI Examiner Configuration under /api/v1/admin/speaking (docs/ADMIN_CONSOLE.md §10).

Reading needs a content permission; editing `content.edit`; publishing `content.publish`.
Configurations reference the existing published Speaking content (no duplicate question store)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.errors import PROBLEM_MEDIA_TYPE
from app.modules.content import api as content
from app.modules.identity import api as identity
from app.modules.identity.api import CurrentUser
from app.modules.speaking import api as speaking

rooms = speaking.rooms
Db = Annotated[AsyncSession, Depends(get_db_session)]
READERS = ("content.edit", "content.review", "content.publish")
Reader = Annotated[CurrentUser, Depends(identity.require_staff_permission(*READERS))]
Editor = Annotated[CurrentUser, Depends(identity.require_staff_permission("content.edit"))]
Publisher = Annotated[CurrentUser, Depends(identity.require_staff_permission("content.publish"))]


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _problems(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: {"description": "Problem", "content": {PROBLEM_MEDIA_TYPE: {}}} for c in codes}


router = APIRouter(
    prefix="/api/v1/admin/speaking",
    tags=["admin-speaking"],
    dependencies=[Depends(_no_store)],
    responses=_problems(401, 403),
)


class ProfileOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    title: str
    personality: str
    speaking_style: str
    accent: str | None
    difficulty: str
    avatar_tone: str
    voice: dict[str, Any]
    is_active: bool
    sort_order: int


class ConfigOut(BaseModel):
    id: uuid.UUID
    test_id: uuid.UUID
    test_version_id: uuid.UUID
    test_title: str
    title: str
    status: str
    revision: datetime
    published_at: datetime | None
    body: rooms.ExaminerConfigBody
    issues: list[str]


class ExaminerPreviewOut(BaseModel):
    issues: list[str]
    rules: list[str]
    plan: list[dict[str, Any]]
    available: dict[str, Any]


class CreateConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test_id: uuid.UUID


class SpeakingTestOptionOut(BaseModel):
    test_id: uuid.UUID
    title: str


def _profile(p: Any) -> ProfileOut:
    return ProfileOut(**{k: getattr(p, k) for k in ProfileOut.model_fields})


async def _config(db: AsyncSession, c: Any) -> ConfigOut:
    body = rooms.ExaminerConfigBody.model_validate(c.config)
    preview = await rooms.preview(db, c)
    return ConfigOut(
        id=c.id,
        test_id=c.test_id,
        test_version_id=c.test_version_id,
        test_title=await content.delivery.test_title_for_version(db, c.test_version_id),
        title=c.title,
        status=c.status,
        revision=c.updated_at,
        published_at=c.published_at,
        body=body,
        issues=preview["issues"],
    )


@router.get("/examiners", response_model=list[ProfileOut])
async def examiners(db: Db, _: Reader) -> list[ProfileOut]:
    async with db.begin():
        return [_profile(p) for p in await rooms.list_profiles(db)]


@router.put("/examiners/{profile_id}", response_model=ProfileOut, responses=_problems(404))
async def update_examiner(
    profile_id: uuid.UUID, body: rooms.ProfileIn, db: Db, user: Editor
) -> ProfileOut:
    async with db.begin():
        return _profile(await rooms.update_profile(db, profile_id, body, actor_id=user.id))


@router.get("/tests", response_model=list[SpeakingTestOptionOut])
async def speaking_tests(db: Db, _: Reader) -> list[SpeakingTestOptionOut]:
    """Published Speaking tests a configuration can be built on."""
    async with db.begin():
        rows = await content.delivery.published_listening_tests(db, module="speaking")
    return [SpeakingTestOptionOut(test_id=t.test_id, title=t.title) for t in rows]


@router.get("/configs", response_model=list[ConfigOut])
async def configs(db: Db, _: Reader) -> list[ConfigOut]:
    async with db.begin():
        return [await _config(db, c) for c in await rooms.list_configs(db)]


@router.post(
    "/configs",
    response_model=ConfigOut,
    status_code=status.HTTP_201_CREATED,
    responses=_problems(422),
)
async def create_config(body: CreateConfigIn, db: Db, user: Editor) -> ConfigOut:
    async with db.begin():
        return await _config(db, await rooms.create_config(db, body.test_id, actor_id=user.id))


@router.get("/configs/{config_id}", response_model=ConfigOut, responses=_problems(404))
async def get_config(config_id: uuid.UUID, db: Db, _: Reader) -> ConfigOut:
    async with db.begin():
        return await _config(db, await rooms.get_config(db, config_id))


@router.put("/configs/{config_id}", response_model=ConfigOut, responses=_problems(404, 409, 422))
async def save_config(
    config_id: uuid.UUID, body: rooms.SaveConfigIn, db: Db, user: Editor
) -> ConfigOut:
    async with db.begin():
        config, _ = await rooms.save_config(db, config_id, body, actor_id=user.id)
        return await _config(db, config)


@router.delete(
    "/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_problems(404, 409)
)
async def delete_config(config_id: uuid.UUID, db: Db, user: Editor) -> None:
    async with db.begin():
        await rooms.delete_config(db, config_id, actor_id=user.id)


@router.get(
    "/configs/{config_id}/preview", response_model=ExaminerPreviewOut, responses=_problems(404)
)
async def preview_config(config_id: uuid.UUID, db: Db, _: Reader) -> ExaminerPreviewOut:
    async with db.begin():
        return ExaminerPreviewOut(**await rooms.preview(db, await rooms.get_config(db, config_id)))


@router.post(
    "/configs/{config_id}/publish", response_model=ConfigOut, responses=_problems(404, 409, 422)
)
async def publish(config_id: uuid.UUID, db: Db, user: Publisher) -> ConfigOut:
    async with db.begin():
        return await _config(db, await rooms.set_published(db, config_id, True, actor_id=user.id))


@router.post(
    "/configs/{config_id}/unpublish", response_model=ConfigOut, responses=_problems(404, 409)
)
async def unpublish(config_id: uuid.UUID, db: Db, user: Publisher) -> ConfigOut:
    async with db.begin():
        return await _config(db, await rooms.set_published(db, config_id, False, actor_id=user.id))
