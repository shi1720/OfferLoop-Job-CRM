"""Application CRUD, status transitions, paste-a-link capture, soft delete
with restore, and per-application interview prep."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import User, get_current_user
from ..config import Settings, get_settings
from ..deps import get_intelligence, get_repo
from ..models import (
    Application,
    ApplicationCreate,
    ApplicationUpdate,
    CapturedPosting,
    CaptureRequest,
    PrepPack,
    Profile,
    Status,
    StatusChange,
    utcnow,
)
from ..repos.base import Repo
from ..services import engine
from ..services.capture import CaptureError, capture_posting
from ..services.llm import DraftContext, GeminiError, Intelligence

router = APIRouter(prefix="/api/applications", tags=["applications"])


def _get_live(repo: Repo, uid: str, app_id: str) -> Application:
    app = repo.get_application(uid, app_id)
    if app is None or app.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.get("")
def list_applications(user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    return repo.list_applications(user.uid)


@router.post("/capture", response_model=CapturedPosting)
def capture(
    payload: CaptureRequest,
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
    server: Intelligence = Depends(get_intelligence),
    settings: Settings = Depends(get_settings),
):
    """Paste a posting URL (or the JD text) → structured fields to confirm.

    Extraction is degradable: with no key and no allowance it falls back to
    regex heuristics rather than blocking — capture always answers.
    """
    if not payload.url.strip() and not payload.text.strip():
        raise HTTPException(status_code=422, detail="Provide a posting URL or the description text")
    profile = repo.get_profile(user.uid) or Profile(uid=user.uid, name=user.name)
    chosen, _source = engine.engine_for(settings, server, profile)
    try:
        return capture_posting(chosen, url=payload.url, text=payload.text)
    except CaptureError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("", status_code=201)
def create_application(
    payload: ApplicationCreate,
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
):
    now = utcnow()
    app = Application(
        uid=user.uid,
        company=payload.company.strip(),
        role=payload.role.strip(),
        location=payload.location.strip(),
        job_type=payload.job_type.strip(),
        description=payload.description.strip(),
        skills=[s.strip() for s in payload.skills if s.strip()][:8],
        posting_url=payload.posting_url.strip(),
        contact_name=payload.contact_name.strip(),
        contact_email=payload.contact_email.strip(),
        applied_at=payload.applied_at or now,
        status=payload.status,
        notes=payload.notes,
        status_history=[StatusChange(to_status=payload.status, at=payload.applied_at or now, note="created")],
    )
    if not app.role:
        raise HTTPException(status_code=422, detail="role is required")
    repo.put_application(app)
    profile = repo.get_profile(user.uid) or Profile(uid=user.uid, name=user.name)
    engine.award(repo, profile, "application_logged")
    return app


@router.get("/{app_id}")
def get_application(app_id: str, user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    return _get_live(repo, user.uid, app_id)


@router.patch("/{app_id}")
def update_application(
    app_id: str,
    payload: ApplicationUpdate,
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
):
    app = _get_live(repo, user.uid, app_id)

    for field in (
        "company",
        "role",
        "location",
        "job_type",
        "description",
        "notes",
        "posting_url",
        "contact_name",
        "contact_email",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(app, field, value)

    if payload.clear_interview:
        app.interview_at = None
    elif payload.interview_at is not None:
        app.interview_at = payload.interview_at

    if payload.status is not None and payload.status != app.status:
        # Every phase transition is recorded — the persistent state history
        # the problem statement asks for, and the input to analytics.
        first_time = all(change.to_status != payload.status for change in app.status_history)
        app.status_history.append(
            StatusChange(from_status=app.status, to_status=payload.status, at=utcnow(), note=payload.status_note)
        )
        app.status = payload.status
        if first_time and payload.status in (Status.INTERVIEW, Status.OFFER):
            profile = repo.get_profile(user.uid) or Profile(uid=user.uid, name=user.name)
            event = "reached_interview" if payload.status == Status.INTERVIEW else "reached_offer"
            engine.award(repo, profile, event)

    app.touch()
    repo.put_application(app)
    return app


@router.post("/{app_id}/prep")
def generate_prep(
    app_id: str,
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
    server: Intelligence = Depends(get_intelligence),
    settings: Settings = Depends(get_settings),
):
    """Interview prep pack: likely questions + STAR stories from the user's
    own proof points. Same engine gating and allowance as draft generation."""
    app = _get_live(repo, user.uid, app_id)
    profile = repo.get_profile(user.uid) or Profile(uid=user.uid, name=user.name)
    intelligence, source = engine.engine_for(settings, server, profile)
    if source == engine.KEY_REQUIRED:
        raise HTTPException(status_code=402, detail=engine.key_required_detail(settings))

    ctx = DraftContext(
        kind="prep",
        role=app.role,
        company=app.company,
        description=app.description,
        skills=app.skills,
        profile_headline=profile.headline,
        profile_years=profile.years_experience,
        profile_skills=profile.skills,
        profile_achievements=profile.achievements,
    )
    try:
        parsed, model = intelligence.prep_pack(ctx)
    except GeminiError as exc:
        status_code, detail = engine.gemini_error_detail(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc

    first_pack = app.prep_pack is None
    app.prep_pack = PrepPack(**parsed, model=model)
    # Prep is preparation, not outreach — deliberately not touching the
    # staleness clock that drives the follow-up cadence.
    app.updated_at = utcnow()
    repo.put_application(app)

    if source == engine.FREE_CREDITS:
        profile.free_used += 1
        repo.put_profile(profile)
    if first_pack:
        engine.award(repo, profile, "prep_generated")
    return app.prep_pack


@router.delete("/{app_id}", status_code=204)
def delete_application(app_id: str, user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    """Soft delete — the Undo toast calls restore within the same session."""
    if not repo.delete_application(user.uid, app_id):
        raise HTTPException(status_code=404, detail="Application not found")


@router.post("/{app_id}/restore")
def restore_application(app_id: str, user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    app = repo.restore_application(user.uid, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app
