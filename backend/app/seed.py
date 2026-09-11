"""Demo-mode seed.

The seed deliberately dogfoods the evaluation pipeline: it boots by
ingesting ``data/sample_postings.csv`` and ``data/sample_drafts.csv``
through the exact same importer the judges will exercise, then curates a
believable few weeks of job-search history on top (stage transitions,
sent follow-ups) and runs one nudge scan so the inbox is alive on first
load.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from .auth import DEMO_UID
from .config import Settings
from .models import Profile, Status, StatusChange, utcnow
from .repos.base import Repo
from .services.ingest import run_import
from .services.llm import Intelligence
from .services.nudges import scan_user

log = logging.getLogger("offerloop.seed")


def _data_dir(settings: Settings) -> Path:
    if settings.data_dir:
        return Path(settings.data_dir)
    return Path(__file__).resolve().parents[2] / "data"


# external_id -> (days since applied, final status, days since last transition)
_STORY: dict[str, tuple[int, Status, int]] = {
    "1": (6, Status.APPLIED, 6),      # quiet past the 5-day cadence → nudge due
    "2": (3, Status.APPLIED, 3),      # fresh, no nudge yet
    "3": (12, Status.INTERVIEW, 2),   # thank-you nudge due
    "4": (21, Status.OFFER, 4),       # offer-response nudge due
    "5": (18, Status.REJECT, 5),      # feedback nudge due
    "6": (9, Status.INTERVIEW, 1),
    "7": (14, Status.APPLIED, 14),    # deep in the follow-up cadence
    "8": (2, Status.APPLIED, 2),
    "9": (26, Status.APPLIED, 26),
    "10": (11, Status.REJECT, 8),
    "11": (31, Status.APPLIED, 31),
    "12": (1, Status.APPLIED, 1),
}


def seed_demo(repo: Repo, intelligence: Intelligence, settings: Settings) -> None:
    if not repo.is_empty(DEMO_UID):
        return

    data = _data_dir(settings)
    postings = data / "sample_postings.csv"
    drafts = data / "sample_drafts.csv"
    if not postings.exists():
        log.warning("seed skipped: %s not found", postings)
        return

    repo.put_profile(
        Profile(
            uid=DEMO_UID,
            name="Shivam Gupta",
            headline="Backend engineer — Python, distributed systems, GCP",
            years_experience=4,
            skills=["Python", "FastAPI", "PostgreSQL", "Kafka", "GCP", "Docker"],
            achievements=(
                "Cut p95 API latency 40% by redesigning a caching layer; "
                "led a 3-engineer pod that shipped a payments reconciliation service "
                "processing 2M events/day"
            ),
        )
    )

    report = run_import(
        repo,
        intelligence,
        DEMO_UID,
        postings=(postings.read_bytes(), postings.name),
        drafts=(drafts.read_bytes(), drafts.name) if drafts.exists() else None,
    )
    log.info(
        "seed import: %d postings, %d drafts (%d linked)",
        report.postings.accepted,
        report.drafts.accepted,
        report.linked_drafts,
    )

    # Curate a believable history on top of the imported rows.
    now = utcnow()
    for external_id, (age_days, status, transition_age) in _STORY.items():
        app = repo.get_application_by_external_id(DEMO_UID, external_id)
        if app is None:
            continue
        applied_at = now - timedelta(days=age_days, hours=3)
        app.applied_at = applied_at
        app.created_at = applied_at
        app.status_history = [StatusChange(to_status=Status.APPLIED, at=applied_at, note="imported")]
        app.last_activity_at = applied_at
        if status != Status.APPLIED:
            moved_at = now - timedelta(days=transition_age, hours=1)
            mid = Status.INTERVIEW
            if status in (Status.OFFER, Status.REJECT) and age_days - transition_age > 3:
                interviewed_at = applied_at + timedelta(days=max(1, (age_days - transition_age) // 2))
                app.status_history.append(
                    StatusChange(from_status=Status.APPLIED, to_status=mid, at=interviewed_at)
                )
                previous = mid
            else:
                previous = Status.APPLIED
            app.status_history.append(StatusChange(from_status=previous, to_status=status, at=moved_at))
            app.status = status
            app.last_activity_at = moved_at
        repo.put_application(app)

    # Re-time imported drafts to sit near their (re-timed) applications so
    # the weekly analytics read like a real few weeks of job hunting.
    apps_by_id = {app.id: app for app in repo.list_applications(DEMO_UID)}
    for draft in repo.list_drafts(DEMO_UID):
        parent = apps_by_id.get(draft.application_id)
        if draft.source != "imported" or parent is None:
            continue
        offset = timedelta(hours=2) if draft.type.value == "cover_letter" else timedelta(days=4)
        draft.created_at = min(parent.applied_at + offset, now - timedelta(hours=1))
        draft.updated_at = draft.created_at
        repo.put_draft(draft)

    # One scan so the nudge inbox is populated the moment the demo opens.
    scan = scan_user(repo, intelligence, settings, DEMO_UID)
    log.info("seed scan: %d nudges, %d drafts", scan.nudges_created, scan.drafts_generated)
