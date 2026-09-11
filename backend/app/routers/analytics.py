"""Analytics + profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import User, get_current_user
from ..config import Settings, get_settings
from ..deps import get_repo
from ..models import Profile, ProfileUpdate
from ..repos.base import Repo
from ..services.analytics import summarize

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics")
def analytics(
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
    settings: Settings = Depends(get_settings),
):
    return summarize(repo, settings, user.uid)


@router.get("/profile")
def get_profile(user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    return repo.get_profile(user.uid) or Profile(uid=user.uid, name=user.name)


@router.put("/profile")
def put_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
):
    profile = repo.get_profile(user.uid) or Profile(uid=user.uid, name=user.name)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(profile, field, value)
    repo.put_profile(profile)
    return profile
