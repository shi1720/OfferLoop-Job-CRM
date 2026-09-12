"""AI engine selection + bring-your-own-key plumbing.

Public deployments can't run everyone's generations on the operator's
key forever, so the engine for any request is chosen in this order:

1. **The user's own Gemini key** (stored encrypted, never returned) —
   unlimited, their quota, their errors surfaced clearly.
2. **The server key, while the user's free allowance lasts**
   (``OFFERLOOP_FREE_GENERATIONS``, default 30 drafts) — the "first taste".
3. **Nothing** — generation returns a structured ``key_required`` error the
   UI turns into an "add your free Gemini key" prompt. Import extraction
   and retrieval degrade gracefully (regex/lexical) instead of blocking.

Demo mode is untouched: the deterministic template writer, no limits.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from ..config import Settings
from ..models import Profile, PublicProfile
from .llm import GeminiIntelligence, Intelligence, TemplateIntelligence

log = logging.getLogger("offerloop.engine")

# ---------------------------------------------------------------------------
# Key storage: Fernet when OFFERLOOP_KEY_SECRET is set, tagged plaintext
# otherwise (Firestore is still encrypted at rest; the env secret adds
# application-layer encryption on top).
# ---------------------------------------------------------------------------


def _fernet(settings: Settings):
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(settings.key_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_key(settings: Settings, raw: str) -> str:
    raw = raw.strip()
    if settings.key_secret:
        return "enc:" + _fernet(settings).encrypt(raw.encode()).decode()
    # deploy.sh always sets OFFERLOOP_KEY_SECRET in production; this path is
    # local development only, and it should never be quiet about it.
    log.warning("OFFERLOOP_KEY_SECRET is not set — storing user key with only at-rest encryption")
    return "raw:" + raw


def decrypt_key(settings: Settings, stored: str) -> str | None:
    if not stored:
        return None
    try:
        if stored.startswith("enc:"):
            return _fernet(settings).decrypt(stored[4:].encode()).decode()
        if stored.startswith("raw:"):
            return stored[4:]
    except Exception:  # noqa: BLE001 — rotated secret etc.: treat as no key
        log.warning("stored user key could not be decrypted (key_secret changed?)")
    return None


def mask_key(raw: str) -> str:
    return f"•••• {raw[-4:]}" if len(raw) >= 8 else "••••"


def validate_gemini_key(settings: Settings, raw: str) -> tuple[bool, str]:
    """Live-check a key against the Gemini API. Returns (ok, message)."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=raw.strip(), http_options=types.HttpOptions(timeout=10000))
        next(iter(client.models.list()), None)
        return True, "Key verified with the Gemini API."
    except Exception as exc:  # noqa: BLE001
        text = str(exc)
        if "API_KEY_INVALID" in text or "API key not valid" in text:
            return False, "That key was rejected by the Gemini API — check for missing characters."
        if "PERMISSION_DENIED" in text:
            return False, "The key is valid but not permitted to use the Gemini API."
        return False, "Couldn't reach the Gemini API to verify the key — try again in a moment."


# ---------------------------------------------------------------------------
# Engine selection
# ---------------------------------------------------------------------------

# source values the rest of the app switches on
YOUR_KEY = "your_key"
FREE_CREDITS = "free_credits"
KEY_REQUIRED = "key_required"
DEMO = "demo"

_user_engines: dict[str, GeminiIntelligence] = {}  # cache key: uid + key fingerprint


def _user_engine(settings: Settings, uid: str, raw_key: str) -> GeminiIntelligence:
    cache_key = f"{uid}:{hashlib.sha256(raw_key.encode()).hexdigest()[:12]}"
    engine = _user_engines.get(cache_key)
    if engine is None:
        engine = GeminiIntelligence(
            api_key=raw_key,
            model_flash=settings.model_flash,
            model_pro=settings.model_pro,
            fallbacks=[m.strip() for m in settings.model_fallbacks.split(",") if m.strip()],
            model_embed=settings.model_embed,
            embed_dim=settings.embed_dim,
            timeout_ms=settings.gemini_timeout_ms,
        )
        if len(_user_engines) > 256:  # crude LRU: reset rather than grow unbounded
            _user_engines.clear()
        _user_engines[cache_key] = engine
    return engine


def engine_source(settings: Settings, server: Intelligence, profile: Profile) -> str:
    if settings.app_mode == "demo":
        return DEMO
    if decrypt_key(settings, profile.gemini_api_key_enc):
        return YOUR_KEY
    if settings.gemini_enabled and profile.free_used < settings.free_generations:
        return FREE_CREDITS
    return KEY_REQUIRED


def engine_for(settings: Settings, server: Intelligence, profile: Profile) -> tuple[Intelligence, str]:
    """The engine to use for GENERATION, plus its source tag.

    ``key_required`` still returns the template engine — callers that must
    block (draft generation) check the source; callers that can degrade
    (extraction, embeddings) just use what they're given.
    """
    source = engine_source(settings, server, profile)
    if source == YOUR_KEY:
        raw = decrypt_key(settings, profile.gemini_api_key_enc)
        return _user_engine(settings, profile.uid, raw or ""), source
    if source == FREE_CREDITS:
        return server, source
    if source == DEMO:
        return server, source
    return TemplateIntelligence(), source


# ---------------------------------------------------------------------------
# Momentum (points) — awarded server-side only
# ---------------------------------------------------------------------------

POINTS = {
    "application_logged": 10,
    "draft_sent": 15,
    "prep_generated": 15,
    "nudge_done": 20,
    "import_completed": 25,
    "reached_interview": 30,
    "reached_offer": 100,
}

LEVELS = [(0, "Starter"), (100, "Consistent"), (300, "Relentless"), (750, "Closer"), (1500, "Legend")]


def level_for(points: int) -> str:
    name = LEVELS[0][1]
    for threshold, title in LEVELS:
        if points >= threshold:
            name = title
    return name


def award(repo, profile: Profile, event: str) -> Profile:
    delta = POINTS.get(event, 0)
    if delta:
        profile.points += delta
        repo.put_profile(profile)
    return profile


# ---------------------------------------------------------------------------
# Shared HTTP mapping for generation endpoints (drafts, prep packs)
# ---------------------------------------------------------------------------

GEMINI_HTTP = {"key_invalid": 400, "quota_exhausted": 429, "timeout": 504, "unavailable": 502}
GEMINI_MESSAGES = {
    "key_invalid": "Your Gemini API key was rejected. Update it under Profile → AI engine.",
    "quota_exhausted": (
        "Your Gemini key's quota is exhausted — free-tier limits reset daily. "
        "Try again later, or use a key from a project with billing."
    ),
    "timeout": "Gemini took too long to respond. Try again in a moment.",
    "unavailable": "The AI engine is unavailable right now. Try again shortly.",
}
GEMINI_FALLBACK_MESSAGE = "The AI engine returned an unexpected error. Try again shortly."


def gemini_error_detail(exc) -> tuple[int, dict]:
    """(status_code, detail) for a GeminiError — .get() so a future unmapped
    code degrades to a 502, never a bare 500."""
    return (
        GEMINI_HTTP.get(exc.code, 502),
        {"code": f"gemini_{exc.code}", "message": GEMINI_MESSAGES.get(exc.code, GEMINI_FALLBACK_MESSAGE)},
    )


def key_required_detail(settings: Settings) -> dict:
    return {
        "code": "key_required",
        "message": (
            f"You've used all {settings.free_generations} free AI drafts. Add your own "
            "free Gemini API key under Profile → AI engine to keep generating."
        ),
    }


def public_profile(settings: Settings, server: Intelligence, profile: Profile) -> PublicProfile:
    raw = decrypt_key(settings, profile.gemini_api_key_enc)
    return PublicProfile(
        uid=profile.uid,
        name=profile.name,
        headline=profile.headline,
        years_experience=profile.years_experience,
        skills=profile.skills,
        tone=profile.tone,
        achievements=profile.achievements,
        style_rules=profile.style_rules,
        onboarded=profile.onboarded,
        points=profile.points,
        level=level_for(profile.points),
        gemini_key_masked=mask_key(raw) if raw else None,
        free_remaining=max(0, settings.free_generations - profile.free_used),
        engine=engine_source(settings, server, profile),
        weekly_goal=profile.weekly_goal,
        push_enabled=bool(profile.push_tokens),
    )
