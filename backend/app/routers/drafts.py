"""Drafts: list, edit, mark sent, and generate with Gemini."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import User, get_current_user
from ..config import Settings, get_settings
from ..deps import get_intelligence, get_repo
from ..models import DraftStatus, DraftUpdate, GenerateRequest, Profile, utcnow
from ..repos.base import Repo
from ..services import engine
from ..services.generation import generate_draft
from ..services.llm import GeminiError, Intelligence

router = APIRouter(prefix="/api", tags=["drafts"])

_GEMINI_HTTP = {"key_invalid": 400, "quota_exhausted": 429, "timeout": 504, "unavailable": 502}
_GEMINI_FALLBACK_MESSAGE = "The AI engine returned an unexpected error. Try again shortly."
_GEMINI_MESSAGES = {
    "key_invalid": "Your Gemini API key was rejected. Update it under Profile → AI engine.",
    "quota_exhausted": (
        "Your Gemini key's quota is exhausted — free-tier limits reset daily. "
        "Try again later, or use a key from a project with billing."
    ),
    "timeout": "Gemini took too long to respond. Try again in a moment.",
    "unavailable": "The AI engine is unavailable right now. Try again shortly.",
}


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
    server: Intelligence = Depends(get_intelligence),
    settings: Settings = Depends(get_settings),
):
    app = repo.get_application(user.uid, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    profile = repo.get_profile(user.uid) or Profile(uid=user.uid, name=user.name)
    intelligence, source = engine.engine_for(settings, server, profile)
    if source == engine.KEY_REQUIRED:
        raise HTTPException(
            status_code=402,
            detail={
                "code": "key_required",
                "message": (
                    f"You've used all {settings.free_generations} free AI drafts. Add your own "
                    "free Gemini API key under Profile → AI engine to keep generating."
                ),
            },
        )

    try:
        draft = generate_draft(repo, intelligence, app, payload.type, instructions=payload.instructions)
    except GeminiError as exc:
        # .get() so a future unmapped code degrades to a 502, never a 500
        raise HTTPException(
            status_code=_GEMINI_HTTP.get(exc.code, 502),
            detail={
                "code": f"gemini_{exc.code}",
                "message": _GEMINI_MESSAGES.get(exc.code, _GEMINI_FALLBACK_MESSAGE),
            },
        ) from exc

    if source == engine.FREE_CREDITS:
        profile.free_used += 1
        repo.put_profile(profile)
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
    # clock that drives the follow-up cadence, and earns momentum.
    if payload.status == DraftStatus.SENT and draft.application_id:
        app = repo.get_application(user.uid, draft.application_id)
        if app:
            app.touch()
            repo.put_application(app)
        profile = repo.get_profile(user.uid) or Profile(uid=user.uid, name=user.name)
        engine.award(repo, profile, "draft_sent")

    return draft.model_dump(exclude={"embedding"})
