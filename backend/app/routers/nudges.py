"""Nudge inbox."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import User, get_current_user
from ..deps import get_repo
from ..models import NudgeStatus
from ..repos.base import Repo

router = APIRouter(prefix="/api/nudges", tags=["nudges"])


@router.get("")
def list_nudges(
    status: str | None = None,
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
):
    return repo.list_nudges(user.uid, status)


@router.post("/{nudge_id}/done")
def mark_done(nudge_id: str, user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    return _set_status(repo, user.uid, nudge_id, NudgeStatus.DONE)


@router.post("/{nudge_id}/dismiss")
def dismiss(nudge_id: str, user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    return _set_status(repo, user.uid, nudge_id, NudgeStatus.DISMISSED)


def _set_status(repo: Repo, uid: str, nudge_id: str, status: NudgeStatus):
    nudge = repo.get_nudge(uid, nudge_id)
    if nudge is None:
        raise HTTPException(status_code=404, detail="Nudge not found")
    nudge.status = status
    repo.update_nudge(nudge)
    return nudge
