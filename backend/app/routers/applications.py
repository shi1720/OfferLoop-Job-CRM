"""Application CRUD + status transitions (the pipeline board's API)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import User, get_current_user
from ..deps import get_repo
from ..models import (
    Application,
    ApplicationCreate,
    ApplicationUpdate,
    Profile,
    Status,
    StatusChange,
    utcnow,
)
from ..repos.base import Repo
from ..services import engine

router = APIRouter(prefix="/api/applications", tags=["applications"])


@router.get("")
def list_applications(user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    return repo.list_applications(user.uid)


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
    app = repo.get_application(user.uid, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.patch("/{app_id}")
def update_application(
    app_id: str,
    payload: ApplicationUpdate,
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
):
    app = repo.get_application(user.uid, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    for field in ("company", "role", "location", "job_type", "description", "notes"):
        value = getattr(payload, field)
        if value is not None:
            setattr(app, field, value)

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


@router.delete("/{app_id}", status_code=204)
def delete_application(app_id: str, user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    if not repo.delete_application(user.uid, app_id):
        raise HTTPException(status_code=404, detail="Application not found")
