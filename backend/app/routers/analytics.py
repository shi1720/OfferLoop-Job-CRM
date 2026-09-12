"""Analytics + profile + AI-engine (bring-your-own-key) endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import User, get_current_user
from ..config import Settings, get_settings
from ..deps import get_intelligence, get_repo
from ..models import GeminiKeyUpdate, Profile, ProfileUpdate, PublicProfile
from ..repos.base import Repo
from ..services import engine
from ..services.analytics import summarize
from ..services.llm import Intelligence

router = APIRouter(prefix="/api", tags=["analytics"])


def _load_profile(repo: Repo, user: User) -> Profile:
    return repo.get_profile(user.uid) or Profile(uid=user.uid, name=user.name)


@router.get("/analytics")
def analytics(
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
    settings: Settings = Depends(get_settings),
):
    return summarize(repo, settings, user.uid)


@router.get("/profile", response_model=PublicProfile)
def get_profile(
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
    settings: Settings = Depends(get_settings),
    server: Intelligence = Depends(get_intelligence),
):
    return engine.public_profile(settings, server, _load_profile(repo, user))


@router.put("/profile", response_model=PublicProfile)
def put_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
    settings: Settings = Depends(get_settings),
    server: Intelligence = Depends(get_intelligence),
):
    profile = _load_profile(repo, user)
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(profile, field, value)
    repo.put_profile(profile)
    return engine.public_profile(settings, server, profile)


@router.put("/profile/gemini-key", response_model=PublicProfile)
def set_gemini_key(
    payload: GeminiKeyUpdate,
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
    settings: Settings = Depends(get_settings),
    server: Intelligence = Depends(get_intelligence),
):
    """Validate the key against the live Gemini API, then store it encrypted."""
    raw = payload.key.strip()
    if len(raw) < 20:
        raise HTTPException(
            status_code=400,
            detail={"code": "key_invalid", "message": "That doesn't look like a Gemini API key."},
        )
    ok, message = engine.validate_gemini_key(settings, raw)
    if not ok:
        raise HTTPException(status_code=400, detail={"code": "key_invalid", "message": message})
    profile = _load_profile(repo, user)
    profile.gemini_api_key_enc = engine.encrypt_key(settings, raw)
    repo.put_profile(profile)
    return engine.public_profile(settings, server, profile)


@router.delete("/profile/gemini-key", response_model=PublicProfile)
def remove_gemini_key(
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
    settings: Settings = Depends(get_settings),
    server: Intelligence = Depends(get_intelligence),
):
    profile = _load_profile(repo, user)
    profile.gemini_api_key_enc = ""
    repo.put_profile(profile)
    return engine.public_profile(settings, server, profile)
