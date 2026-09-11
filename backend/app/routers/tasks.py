"""Machine endpoints: the Cloud Scheduler-driven nudge scan, health, and
the runtime config the frontend bootstraps from."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth import User, get_current_user, verify_scheduler
from ..config import Settings, get_settings
from ..deps import get_intelligence, get_repo
from ..repos.base import Repo
from ..services.llm import Intelligence
from ..services.nudges import scan_all, scan_user

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(request: Request, settings: Settings = Depends(get_settings)):
    return {
        "status": "ok",
        "mode": settings.app_mode,
        "intelligence": request.app.state.intelligence.name,
        "models": {"flash": settings.model_flash, "pro": settings.model_pro},
    }


@router.get("/config")
def config(settings: Settings = Depends(get_settings)):
    """Public bootstrap config for the frontend (no secrets)."""
    import json

    firebase = {}
    if settings.firebase_web_config:
        try:
            firebase = json.loads(settings.firebase_web_config)
        except ValueError:
            firebase = {}
    return {
        "mode": settings.app_mode,
        "firebase": firebase,
        "cadence": {
            "follow_up_backoff_days": settings.follow_up_backoff,
            "interview_thank_you_days": settings.interview_thank_you_days,
            "offer_response_days": settings.offer_response_days,
            "reject_feedback_days": settings.reject_feedback_days,
            "ghost_after_days": settings.ghost_after_days,
        },
    }


@router.post("/tasks/nudge-scan", dependencies=[Depends(verify_scheduler)])
def nudge_scan(
    repo: Repo = Depends(get_repo),
    intelligence: Intelligence = Depends(get_intelligence),
    settings: Settings = Depends(get_settings),
):
    """Invoked by Cloud Scheduler (OIDC-authenticated) on a fixed cadence.

    Scans every user's pipeline, creates due nudges idempotently, and
    auto-drafts follow-up emails up to a per-run generation budget.
    """
    return scan_all(repo, intelligence, settings)


@router.post("/scan")
def scan_mine(
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
    intelligence: Intelligence = Depends(get_intelligence),
    settings: Settings = Depends(get_settings),
):
    """User-triggered scan of their own pipeline ("Check my pipeline now")."""
    return scan_user(repo, intelligence, settings, user.uid)
