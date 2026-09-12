"""Web push (Firebase Cloud Messaging) — the nudge engine's reach outside
the tab.

Only the *scheduled* scan notifies (a user clicking "scan my pipeline" is
already looking at the result). Dead tokens are pruned on send so an
uninstalled device stops costing a request within one cycle.
"""

from __future__ import annotations

import logging

from ..models import Profile
from ..repos.base import Repo

log = logging.getLogger("offerloop.push")

MAX_TOKENS_PER_USER = 5


def register_token(repo: Repo, profile: Profile, token: str) -> Profile:
    token = token.strip()
    if token and token not in profile.push_tokens:
        profile.push_tokens = (profile.push_tokens + [token])[-MAX_TOKENS_PER_USER:]
        repo.put_profile(profile)
    return profile


def clear_tokens(repo: Repo, profile: Profile) -> Profile:
    if profile.push_tokens:
        profile.push_tokens = []
        repo.put_profile(profile)
    return profile


def notify_nudges(repo: Repo, profile: Profile, nudges_created: int, link: str = "/") -> int:
    """Send 'follow-ups are due' to every registered device. Returns sends."""
    if not profile.push_tokens or nudges_created <= 0:
        return 0
    try:
        from firebase_admin import messaging
    except ImportError:  # demo/local without firebase-admin extras
        return 0

    plural = "s" if nudges_created > 1 else ""
    title = f"{nudges_created} follow-up{plural} due"
    body = "Drafts are ready in OfferLoop — send them while the thread is warm."

    sent = 0
    dead: list[str] = []
    for token in profile.push_tokens:
        message = messaging.Message(
            token=token,
            notification=messaging.Notification(title=title, body=body),
            webpush=messaging.WebpushConfig(
                fcm_options=messaging.WebpushFCMOptions(link=link or "/"),
            ),
        )
        try:
            messaging.send(message)
            sent += 1
        except Exception as exc:  # noqa: BLE001 — one bad device never blocks the rest
            name = type(exc).__name__
            if "Unregistered" in name or "NotFound" in name or "InvalidArgument" in name:
                dead.append(token)
            else:
                log.warning("push send failed for %s…: %s", token[:12], exc)

    if dead:
        profile.push_tokens = [t for t in profile.push_tokens if t not in dead]
        repo.put_profile(profile)
        log.info("pruned %d dead push tokens for %s", len(dead), profile.uid)
    return sent
