"""Drafts: list, edit, mark sent, and generate with Gemini."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import User, get_current_user
from ..deps import get_intelligence, get_repo
from ..models import DraftStatus, DraftUpdate, GenerateRequest, utcnow
from ..repos.base import Repo
from ..services.generation import generate_draft
from ..services.llm import Intelligence

router = APIRouter(prefix="/api", tags=["drafts"])


@router.get("/drafts")
def list_drafts(
    application_id: str | None = None,
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
):
    drafts = repo.list_drafts(user.uid, application_id)
    # embeddings are an internal detail — keep payloads light
    return [d.model_dump(exclude={"embedding"}) for d in drafts]


@router.post("/applications/{app_id}/drafts", status_code=201)
def generate(
    app_id: str,
    payload: GenerateRequest,
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
    intelligence: Intelligence = Depends(get_intelligence),
):
    app = repo.get_application(user.uid, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    draft = generate_draft(repo, intelligence, app, payload.type, instructions=payload.instructions)
    return draft.model_dump(exclude={"embedding"})


@router.patch("/drafts/{draft_id}")
def update_draft(
    draft_id: str,
    payload: DraftUpdate,
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
):
    draft = repo.get_draft(user.uid, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    if payload.subject is not None:
        draft.subject = payload.subject
    if payload.contents is not None and payload.contents != draft.contents:
        draft.contents = payload.contents
        if draft.source == "generated":
            draft.source = "edited"
        draft.embedding = None  # stale once the text changes
    if payload.status is not None:
        draft.status = payload.status
    draft.updated_at = utcnow()
    repo.put_draft(draft)

    # Marking a draft "sent" is real outreach — it resets the staleness
    # clock that drives the follow-up cadence.
    if payload.status == DraftStatus.SENT and draft.application_id:
        app = repo.get_application(user.uid, draft.application_id)
        if app:
            app.touch()
            repo.put_application(app)

    return draft.model_dump(exclude={"embedding"})
