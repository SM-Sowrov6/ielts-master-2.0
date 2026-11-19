"""Admin Listening-management API under /api/v1/admin/content (docs/ADMIN_CONSOLE.md §8).

Permissions (existing RBAC, SECURITY_GUIDELINES.md §4.1): reading any content needs one of the
content permissions; editing needs `content.edit`; review `content.review` (never on one's own
version: four-eyes, enforced by the content service); publish/archive `content.publish`; media
`media.upload`; licences `content.licenses.manage`. Every route also passes the staff gate.

Each request is one transaction. State changes are audited by the content service. Answer keys
appear only in these admin responses, never in student-facing APIs.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.database import get_db_session
from app.core.errors import PROBLEM_MEDIA_TYPE
from app.core.storage import PRESIGN_TTL_SECONDS
from app.modules.admin.content_schemas import (
    AssetOut,
    BookOut,
    CatalogRefOut,
    CreateRubricIn,
    EditionOut,
    EditorDocumentOut,
    IssueOut,
    IssuesOut,
    LicenceOut,
    ListeningOverviewOut,
    ListeningPageOut,
    ListeningRowOut,
    MediaUploadIn,
    MediaUploadOut,
    MediaUrlOut,
    PreviewOut,
    QuestionTypeOut,
    ReviewIn,
    ReviewOut,
    RubricBandOut,
    RubricCriterionOut,
    RubricOut,
    SaveResultOut,
    TestOut,
    VersionOut,
    VersionSummaryOut,
)
from app.modules.content import api as content
from app.modules.identity import api as identity
from app.modules.identity.api import CurrentUser

CONTENT_READERS = ("content.edit", "content.review", "content.publish")

Db = Annotated[AsyncSession, Depends(get_db_session)]
Reader = Annotated[CurrentUser, Depends(identity.require_staff_permission(*CONTENT_READERS))]
Editor = Annotated[CurrentUser, Depends(identity.require_staff_permission("content.edit"))]
Reviewer = Annotated[CurrentUser, Depends(identity.require_staff_permission("content.review"))]
Publisher = Annotated[CurrentUser, Depends(identity.require_staff_permission("content.publish"))]
Uploader = Annotated[CurrentUser, Depends(identity.require_staff_permission("media.upload"))]
LicenceManager = Annotated[
    CurrentUser, Depends(identity.require_staff_permission("content.licenses.manage"))
]


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _problems(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: {"description": "Problem", "content": {PROBLEM_MEDIA_TYPE: {}}} for c in codes}


router = APIRouter(
    prefix="/api/v1/admin/content",
    tags=["admin-content"],
    dependencies=[Depends(_no_store)],
    responses=_problems(401, 403),
)


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _issues(issues: list[content.ValidationIssue]) -> list[IssueOut]:
    return [
        IssueOut(
            severity="error" if i.is_error else "warning",
            code=i.code,
            location=i.location,
            message=i.message,
        )
        for i in issues
    ]


def _asset(a: Any) -> AssetOut:
    return AssetOut(
        id=a.id,
        kind=a.kind,
        status=a.status,
        mime_type=a.mime_type,
        size_bytes=a.size_bytes,
        original_filename=a.original_filename,
    )


def _approved(version: Any) -> bool:
    return version.status == "in_review" and any(
        r.decision == "approved"
        and (version.submitted_at is None or r.created_at >= version.submitted_at)
        and r.reviewer_id != version.created_by
        for r in version.reviews
    )


async def _document(db: AsyncSession, version_id: uuid.UUID) -> EditorDocumentOut:
    doc = await content.authoring.editor_document(db, version_id)
    v = doc.version
    people = {v.created_by, *(r.reviewer_id for r in v.reviews)} - {None}
    names = await identity.display_names(db, {p for p in people if p is not None})
    return EditorDocumentOut(
        test=TestOut(
            id=doc.test.id,
            code=doc.test.code,
            title=doc.test.title,
            admin_notes=doc.test.admin_notes,
            live_version_id=doc.test.current_published_version_id,
        ),
        catalog=CatalogRefOut(
            book_id=doc.book.id,
            book_title=doc.book.title,
            edition_id=doc.edition.id,
            edition_label=doc.edition.edition_label,
            license_id=doc.book.license_id,
        ),
        version=VersionOut(
            id=v.id,
            version_no=v.version_no,
            status=v.status,
            approved=_approved(v),
            revision=v.updated_at,
            created_by=v.created_by,
            created_by_name=names.get(v.created_by) if v.created_by else None,
            change_note=v.change_note,
            description=v.description,
            difficulty=v.difficulty,
            tags=list(v.tags),
            submitted_at=v.submitted_at,
            published_at=v.published_at,
            reviews=[
                ReviewOut(
                    reviewer_id=r.reviewer_id,
                    reviewer_name=names.get(r.reviewer_id),
                    decision=r.decision,
                    comment=r.comment,
                    created_at=r.created_at,
                )
                for r in v.reviews
            ],
        ),
        module=doc.module.module,
        variant=doc.module.variant,
        duration_seconds=doc.module.duration_seconds,
        sections=[
            content.SectionIn.model_validate(content.authoring.section_document(s))
            for s in doc.module.sections
        ],
        writing_tasks=[
            content.WritingTaskIn.model_validate({k: v for k, v in t.items() if k != "task_kind"})
            for t in content.authoring.writing_tasks_document(doc.module)
        ],
        speaking_parts=[
            content.SpeakingPartIn.model_validate(p)
            for p in content.authoring.speaking_parts_document(doc.module)
        ],
        assets=[_asset(a) for a in doc.assets],
        versions=[
            VersionSummaryOut(
                id=x.id, version_no=x.version_no, status=x.status, updated_at=x.updated_at
            )
            for x in doc.versions
        ],
    )


# ------------------------------------------------------------------------------ listing
@router.get("/{module}/overview", response_model=ListeningOverviewOut)
async def listening_overview(
    module: content.ContentModule, db: Db, _: Reader
) -> ListeningOverviewOut:
    async with db.begin():
        data = await content.authoring.listening_overview(db, module)
    return ListeningOverviewOut(total=data.total, **data.by_status)


@router.get("/{module}/tests", response_model=ListeningPageOut)
async def list_listening_tests(
    module: content.ContentModule,
    db: Db,
    _: Reader,
    search: Annotated[str | None, Query(max_length=100)] = None,
    status_filter: Annotated[content.ListStatus | None, Query(alias="status")] = None,
    difficulty: content.Difficulty | None = None,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ListeningPageOut:
    async with db.begin():
        page = await content.authoring.list_listening_tests(
            db,
            search=search,
            status=status_filter,
            difficulty=difficulty,
            offset=offset,
            limit=limit,
            module=module,
        )
        names = await identity.display_names(
            db, {r.created_by for r in page.items if r.created_by is not None}
        )
    return ListeningPageOut(
        items=[
            ListeningRowOut(
                **{
                    k: getattr(r, k) for k in ListeningRowOut.model_fields if k != "created_by_name"
                },
                created_by_name=names.get(r.created_by) if r.created_by else None,
            )
            for r in page.items
        ],
        total=page.total,
        offset=offset,
        limit=limit,
    )


@router.get("/question-types", response_model=list[QuestionTypeOut])
async def question_types(
    _: Reader, module: content.ObjectiveModule = "listening"
) -> list[QuestionTypeOut]:
    """Types of the existing registry usable in the module (canonical codes)."""
    return [
        QuestionTypeOut(code=code, family=family, modules=modules)
        for code, family, modules in content.authoring.listening_question_types(module)
    ]


# ------------------------------------------------------------------------------ catalogue
@router.get("/licences", response_model=list[LicenceOut])
async def licences(db: Db, _: Reader) -> list[LicenceOut]:
    async with db.begin():
        rows = await content.authoring.list_licences(db)
    return [
        LicenceOut(
            id=x.id,
            source_type=x.source_type,
            licensor=x.licensor,
            licence_reference=x.licence_reference,
            valid_from=x.valid_from,
            valid_until=x.valid_until,
        )
        for x in rows
    ]


@router.post("/licences", response_model=LicenceOut, status_code=status.HTTP_201_CREATED)
async def create_licence(body: content.LicenceIn, db: Db, user: LicenceManager) -> LicenceOut:
    async with db.begin():
        x = await content.authoring.create_original_licence(db, body, actor_id=user.id)
    return LicenceOut(
        id=x.id,
        source_type=x.source_type,
        licensor=x.licensor,
        licence_reference=x.licence_reference,
        valid_from=x.valid_from,
        valid_until=x.valid_until,
    )


@router.get("/books", response_model=list[BookOut])
async def books(db: Db, _: Reader) -> list[BookOut]:
    async with db.begin():
        rows = await content.authoring.list_books(db)
    return [
        BookOut(
            id=b.book.id,
            slug=b.book.slug,
            title=b.book.title,
            license_id=b.book.license_id,
            editions=[
                EditionOut(
                    id=e.id,
                    label=e.edition_label,
                    publication_year=e.publication_year,
                    variant=e.variant,
                )
                for e in b.editions
            ],
        )
        for b in rows
    ]


@router.post("/books", response_model=BookOut, status_code=status.HTTP_201_CREATED)
async def create_book(body: content.BookCreateIn, db: Db, user: Editor) -> BookOut:
    async with db.begin():
        b = await content.authoring.create_book(db, body, actor_id=user.id)
    return BookOut(id=b.id, slug=b.slug, title=b.title, license_id=b.license_id, editions=[])


@router.post(
    "/books/{book_id}/editions", response_model=EditionOut, status_code=status.HTTP_201_CREATED
)
async def create_edition(
    book_id: uuid.UUID, body: content.EditionCreateIn, db: Db, user: Editor
) -> EditionOut:
    async with db.begin():
        e = await content.authoring.create_edition(db, book_id, body, actor_id=user.id)
    return EditionOut(
        id=e.id, label=e.edition_label, publication_year=e.publication_year, variant=e.variant
    )


# ------------------------------------------------------------------------------ authoring
@router.post(
    "/{module}/tests",
    response_model=EditorDocumentOut,
    status_code=status.HTTP_201_CREATED,
    responses=_problems(404, 409, 422),
)
async def create_listening_test(
    module: content.ContentModule, body: content.CreateListeningTestIn, db: Db, user: Editor
) -> EditorDocumentOut:
    async with db.begin():
        if module in ("writing", "speaking"):
            version = await content.productive.create_productive_test(
                db, body, actor_id=user.id, module=module, variant=body.variant
            )
        else:
            version = await content.authoring.create_listening_test(
                db, body, actor_id=user.id, module=module
            )
        return await _document(db, version.id)


@router.get("/versions/{version_id}", response_model=EditorDocumentOut, responses=_problems(404))
async def get_version(version_id: uuid.UUID, db: Db, _: Reader) -> EditorDocumentOut:
    async with db.begin():
        return await _document(db, version_id)


@router.put(
    "/versions/{version_id}",
    response_model=SaveResultOut,
    responses=_problems(404, 409, 422),
)
async def save_version(
    version_id: uuid.UUID, body: content.SaveListeningDraftIn, db: Db, user: Editor
) -> SaveResultOut:
    async with db.begin():
        result = await content.authoring.save_listening_draft(
            db, version_id, body, actor_id=user.id
        )
        document = await _document(db, result.version.id)
    return SaveResultOut(document=document, issues=_issues(result.issues))


@router.put(
    "/versions/{version_id}/productive",
    response_model=SaveResultOut,
    responses=_problems(404, 409, 422),
)
async def save_productive_version(
    version_id: uuid.UUID, body: content.SaveProductiveDraftIn, db: Db, user: Editor
) -> SaveResultOut:
    """Save a Writing (tasks) or Speaking (parts) draft, with its model answers."""
    async with db.begin():
        result = await content.productive.save_productive_draft(
            db, version_id, body, actor_id=user.id
        )
        document = await _document(db, result.version.id)
    return SaveResultOut(document=document, issues=_issues(result.issues))


@router.delete(
    "/versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_problems(404, 409),
)
async def delete_version(version_id: uuid.UUID, db: Db, user: Editor) -> None:
    async with db.begin():
        await content.authoring.delete_draft(db, version_id, actor_id=user.id)


@router.get("/versions/{version_id}/validation", response_model=IssuesOut)
async def validate_version(version_id: uuid.UUID, db: Db, _: Reader) -> IssuesOut:
    async with db.begin():
        issues = await content.authoring.validate_for_publish(db, version_id)
    return IssuesOut(issues=_issues(issues), ok=not any(i.is_error for i in issues))


@router.get("/versions/{version_id}/preview", response_model=PreviewOut)
async def preview(version_id: uuid.UUID, db: Db, _: Reader) -> PreviewOut:
    async with db.begin():
        return PreviewOut.model_validate(await content.authoring.admin_preview(db, version_id))


@router.post(
    "/versions/{version_id}/duplicate",
    response_model=EditorDocumentOut,
    status_code=status.HTTP_201_CREATED,
    responses=_problems(404, 409),
)
async def duplicate(
    version_id: uuid.UUID, body: content.DuplicateIn, db: Db, user: Editor
) -> EditorDocumentOut:
    async with db.begin():
        copy = await content.authoring.duplicate_test(db, version_id, body, actor_id=user.id)
        return await _document(db, copy.id)


@router.post(
    "/tests/{test_id}/revisions",
    response_model=EditorDocumentOut,
    status_code=status.HTTP_201_CREATED,
    responses=_problems(404, 409),
)
async def new_revision(test_id: uuid.UUID, db: Db, user: Editor) -> EditorDocumentOut:
    async with db.begin():
        draft = await content.authoring.new_revision(db, test_id, actor_id=user.id)
        return await _document(db, draft.id)


# ------------------------------------------------------------------------------ workflow
@router.post(
    "/versions/{version_id}/submit",
    response_model=EditorDocumentOut,
    responses=_problems(404, 409, 422),
)
async def submit(version_id: uuid.UUID, db: Db, user: Editor) -> EditorDocumentOut:
    async with db.begin():
        await content.authoring.submit(db, version_id, actor_id=user.id)
        return await _document(db, version_id)


@router.post(
    "/versions/{version_id}/review",
    response_model=EditorDocumentOut,
    responses=_problems(404, 409),
)
async def review(
    version_id: uuid.UUID, body: ReviewIn, db: Db, user: Reviewer
) -> EditorDocumentOut:
    async with db.begin():
        await content.authoring.review(
            db,
            version_id,
            reviewer_id=user.id,
            decision=content.ReviewDecision(body.decision),
            comment=body.comment,
        )
        return await _document(db, version_id)


@router.post(
    "/versions/{version_id}/publish",
    response_model=EditorDocumentOut,
    responses=_problems(404, 409, 422),
)
async def publish(version_id: uuid.UUID, db: Db, user: Publisher) -> EditorDocumentOut:
    async with db.begin():
        await content.authoring.publish(db, version_id, actor_id=user.id)
        return await _document(db, version_id)


@router.post(
    "/versions/{version_id}/archive",
    response_model=EditorDocumentOut,
    responses=_problems(404, 409),
)
async def archive(version_id: uuid.UUID, db: Db, user: Publisher) -> EditorDocumentOut:
    async with db.begin():
        await content.authoring.archive(db, version_id, actor_id=user.id)
        return await _document(db, version_id)


# ------------------------------------------------------------------------------ media
@router.post(
    "/media",
    response_model=MediaUploadOut,
    status_code=status.HTTP_201_CREATED,
    responses=_problems(404, 422, 503),
)
async def start_upload(
    body: MediaUploadIn, request: Request, db: Db, user: Uploader
) -> MediaUploadOut:
    settings = _settings(request)
    storage = content.media.storage_for(settings)
    async with db.begin():
        ticket = await content.media.create_upload(
            db,
            storage,
            settings,
            test_id=body.test_id,
            kind=body.kind,
            filename=body.filename,
            mime_type=body.mime_type,
            size_bytes=body.size_bytes,
            sha256=body.sha256.lower(),
            actor_id=user.id,
        )
    return MediaUploadOut(
        asset=_asset(ticket.asset),
        upload_url=ticket.upload_url,
        headers=ticket.headers,
        expires_in_seconds=PRESIGN_TTL_SECONDS,
    )


@router.post(
    "/media/{asset_id}/complete", response_model=AssetOut, responses=_problems(404, 409, 422, 503)
)
async def complete_upload(
    asset_id: uuid.UUID, request: Request, db: Db, user: Uploader
) -> AssetOut:
    settings = _settings(request)
    storage = content.media.storage_for(settings)
    async with db.begin():
        asset, rejection = await content.media.complete_upload(
            db, storage, settings, asset_id=asset_id, actor_id=user.id
        )
        out = _asset(asset)
    if rejection is not None:  # the failed state is committed above
        raise content.MediaRejectedError(rejection)
    return out


@router.get("/media/{asset_id}/url", response_model=MediaUrlOut, responses=_problems(404, 409, 503))
async def media_url(asset_id: uuid.UUID, request: Request, db: Db, _: Reader) -> MediaUrlOut:
    storage = content.media.playback_storage(_settings(request))
    async with db.begin():
        asset, url = await content.media.playback_url(db, storage, asset_id=asset_id)
    return MediaUrlOut(asset=_asset(asset), url=url, expires_in_seconds=PRESIGN_TTL_SECONDS)


# ------------------------------------------------------------------------------ rubrics
async def _rubric(db: AsyncSession, rubric: Any) -> RubricOut:
    people = {rubric.created_by, *(r.reviewer_id for r in rubric.reviews)} - {None}
    names = await identity.display_names(db, {p for p in people if p is not None})
    return RubricOut(
        id=rubric.id,
        module=rubric.module,
        version_no=rubric.version_no,
        title=rubric.title,
        status=rubric.status,
        approved=content.rubrics.approved(rubric),
        revision=rubric.updated_at,
        change_note=rubric.change_note,
        created_by=rubric.created_by,
        created_by_name=names.get(rubric.created_by) if rubric.created_by else None,
        submitted_at=rubric.submitted_at,
        published_at=rubric.published_at,
        criteria=[
            RubricCriterionOut(
                code=c["code"],
                name=c["name"],
                description=c.get("description", ""),
                bands=[RubricBandOut(**b) for b in c.get("bands", [])],
            )
            for c in rubric.criteria
        ],
        reviews=[
            ReviewOut(
                reviewer_id=r.reviewer_id,
                reviewer_name=names.get(r.reviewer_id),
                decision=r.decision,
                comment=r.comment,
                created_at=r.created_at,
            )
            for r in rubric.reviews
        ],
        issues=_issues(content.rubrics.rubric_issues(rubric.module, rubric.criteria)),
    )


@router.get("/rubrics", response_model=list[RubricOut])
async def list_rubrics(module: content.RubricModule, db: Db, _: Reader) -> list[RubricOut]:
    async with db.begin():
        rows = await content.rubrics.list_rubrics(db, module)
        return [await _rubric(db, r) for r in rows]


@router.post(
    "/rubrics",
    response_model=RubricOut,
    status_code=status.HTTP_201_CREATED,
    responses=_problems(409),
)
async def create_rubric(body: CreateRubricIn, db: Db, user: Editor) -> RubricOut:
    async with db.begin():
        rubric = await content.rubrics.create_rubric(db, body.module, actor_id=user.id)
        return await _rubric(db, rubric)


@router.get("/rubrics/{rubric_id}", response_model=RubricOut, responses=_problems(404))
async def get_rubric(rubric_id: uuid.UUID, db: Db, _: Reader) -> RubricOut:
    async with db.begin():
        return await _rubric(db, await content.rubrics.get_rubric(db, rubric_id))


@router.put("/rubrics/{rubric_id}", response_model=RubricOut, responses=_problems(404, 409, 422))
async def save_rubric(
    rubric_id: uuid.UUID, body: content.SaveRubricIn, db: Db, user: Editor
) -> RubricOut:
    async with db.begin():
        rubric, _ = await content.rubrics.save_rubric(db, rubric_id, body, actor_id=user.id)
        return await _rubric(db, rubric)


@router.delete(
    "/rubrics/{rubric_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_problems(404, 409)
)
async def delete_rubric(rubric_id: uuid.UUID, db: Db, user: Editor) -> None:
    async with db.begin():
        await content.rubrics.delete_rubric_draft(db, rubric_id, actor_id=user.id)


@router.post(
    "/rubrics/{rubric_id}/submit", response_model=RubricOut, responses=_problems(404, 409, 422)
)
async def submit_rubric(rubric_id: uuid.UUID, db: Db, user: Editor) -> RubricOut:
    async with db.begin():
        rubric = await content.rubrics.submit_rubric(db, rubric_id, actor_id=user.id)
        return await _rubric(db, rubric)


@router.post("/rubrics/{rubric_id}/review", response_model=RubricOut, responses=_problems(404, 409))
async def review_rubric(rubric_id: uuid.UUID, body: ReviewIn, db: Db, user: Reviewer) -> RubricOut:
    async with db.begin():
        rubric = await content.rubrics.review_rubric(
            db,
            rubric_id,
            reviewer_id=user.id,
            decision=content.ReviewDecision(body.decision),
            comment=body.comment,
        )
        return await _rubric(db, rubric)


@router.post(
    "/rubrics/{rubric_id}/publish", response_model=RubricOut, responses=_problems(404, 409)
)
async def publish_rubric(rubric_id: uuid.UUID, db: Db, user: Publisher) -> RubricOut:
    async with db.begin():
        rubric = await content.rubrics.publish_rubric(db, rubric_id, actor_id=user.id)
        return await _rubric(db, rubric)
