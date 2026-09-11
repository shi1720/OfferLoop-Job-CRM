"""Authentication.

Live mode: the frontend signs in with Firebase Authentication (Google
sign-in) and sends the Firebase ID token as a Bearer header; we verify it
server-side with firebase-admin. Every repo call is namespaced by the
verified ``uid`` — user data isolation is enforced at the storage layer,
not by the client.

Demo mode: a fixed demo identity, so judges can try the product (and CI
can exercise every endpoint) without a Firebase project.

Scheduler endpoints (``/api/tasks/*``) accept only Google-signed OIDC
tokens from the configured service account in live mode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from .config import Settings, get_settings

log = logging.getLogger("offerloop.auth")

DEMO_UID = "demo-user"


@dataclass
class User:
    uid: str
    email: str = ""
    name: str = ""


_firebase_initialized = False


def _verify_firebase_token(token: str) -> User:
    global _firebase_initialized
    import firebase_admin
    from firebase_admin import auth as fb_auth

    if not _firebase_initialized:
        try:
            firebase_admin.get_app()
        except ValueError:
            firebase_admin.initialize_app()  # ADC on Cloud Run
        _firebase_initialized = True

    decoded = fb_auth.verify_id_token(token)
    return User(uid=decoded["uid"], email=decoded.get("email", ""), name=decoded.get("name", ""))


def get_current_user(request: Request, settings: Settings = Depends(get_settings)) -> User:
    header = request.headers.get("Authorization", "")
    token = header.removeprefix("Bearer ").strip()

    if settings.app_mode == "demo":
        # Even the demo workspace authenticates: the fixed token exercises
        # the same 401 path a bad Firebase token takes in live mode.
        if token != "demo":
            raise HTTPException(status_code=401, detail="Demo mode expects `Authorization: Bearer demo`")
        return User(uid=DEMO_UID, email="demo@offerloop.dev", name="Shivam Gupta")

    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        return _verify_firebase_token(token)
    except Exception as exc:  # noqa: BLE001
        log.info("token rejected: %s", exc)
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc


def verify_scheduler(request: Request, settings: Settings = Depends(get_settings)) -> None:
    """Gate for Cloud Scheduler / Cloud Tasks invocations.

    Fails CLOSED: in live mode the endpoint refuses to run unless both the
    expected caller identity and the OIDC audience are configured, the
    token's signature checks out for that audience, and the verified email
    matches the scheduler service account.
    """
    if settings.app_mode == "demo":
        return

    if not settings.scheduler_service_account or not settings.public_url:
        log.error("scheduler auth unconfigured (scheduler_service_account/public_url) — refusing scan")
        raise HTTPException(status_code=403, detail="Scheduler authentication not configured")

    header = request.headers.get("Authorization", "")
    token = header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing OIDC token")
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token

        claims = id_token.verify_oauth2_token(
            token, google_requests.Request(), audience=settings.public_url
        )
        if not claims.get("email_verified"):
            raise ValueError("caller email not verified")
        if claims.get("email") != settings.scheduler_service_account:
            raise ValueError(f"unexpected caller: {claims.get('email')}")
    except Exception as exc:  # noqa: BLE001
        log.warning("scheduler auth rejected: %s", exc)
        raise HTTPException(status_code=403, detail="Caller not authorized") from exc
