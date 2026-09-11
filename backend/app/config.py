"""Application configuration.

Every knob lives here so the same container image runs in three contexts:

- ``demo``  : zero-credential mode. In-memory store, deterministic writer,
              a seeded demo workspace. Used for local dev, CI, and judges
              who want to try the app without a GCP project.
- ``live``  : full GCP mode. Firestore, Firebase Auth, Gemini on Vertex AI
              (or the Gemini API key), Cloud Scheduler-driven nudges.
- tests     : demo mode with a fixed clock and no seed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OFFERLOOP_", env_file=".env", extra="ignore")

    # --- runtime mode -----------------------------------------------------
    app_mode: Literal["demo", "live"] = "demo"
    demo_seed: bool = True
    static_dir: str = ""  # built frontend; auto-detected when empty
    data_dir: str = ""  # sample CSVs for the demo seed; auto-detected when empty

    # --- GCP / data -------------------------------------------------------
    gcp_project: str = ""
    firestore_database: str = "(default)"

    # --- Gemini -----------------------------------------------------------
    # Model routing: Flash handles high-volume structured work (posting
    # extraction, follow-up drafts, nudge copy); Pro handles the highest
    # stakes artifact, the cover letter. Both fall back gracefully.
    gemini_api_key: str = ""
    use_vertex: bool = False
    vertex_location: str = "global"
    model_flash: str = "gemini-3.7-flash"
    model_pro: str = "gemini-3.1-pro-preview"
    # Fallbacks verified live against the Gemini API: the 2.5 family is
    # retired for new projects; 3.6-flash is Google's recommended successor.
    model_fallbacks: str = "gemini-3.6-flash,gemini-3.5-flash-lite"
    model_embed: str = "gemini-embedding-001"
    embed_dim: int = 768
    # A model that HANGS (observed on free-tier keys for flagship models)
    # would defeat the fallback chain without a hard per-call timeout.
    gemini_timeout_ms: int = 45000

    # --- Firebase Auth ----------------------------------------------------
    # JSON web config passed straight to the frontend via /api/config.
    firebase_web_config: str = ""

    # --- Nudge cadence ----------------------------------------------------
    # Sales-style touch cadence: first follow-up after 5 quiet days, then
    # backoff. Every value is a product decision surfaced in the UI.
    follow_up_backoff_days: str = "5,7,10"
    interview_thank_you_days: int = 1
    offer_response_days: int = 3
    reject_feedback_days: int = 2
    ghost_after_days: int = 21
    max_generated_per_scan: int = 25

    # --- Cloud Scheduler / Tasks -----------------------------------------
    scheduler_service_account: str = ""
    tasks_queue: str = ""
    tasks_location: str = "asia-south1"
    public_url: str = ""

    @property
    def follow_up_backoff(self) -> list[int]:
        return [int(x) for x in self.follow_up_backoff_days.split(",") if x.strip()]

    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key) or self.use_vertex


@lru_cache
def get_settings() -> Settings:
    return Settings()
