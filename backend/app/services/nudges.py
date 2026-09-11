"""The nudge engine — sales-cadence discipline for a job search.

Cloud Scheduler hits ``POST /api/tasks/nudge-scan`` on a fixed schedule;
this module decides who deserves a nudge. Four rules, all deterministic
and all visible to the user in the UI (no black box):

- ``follow_up``           Applied and quiet for too long → nudge with an
                          auto-drafted follow-up email attached. Runs as a
                          3-touch cadence with backoff (5, 7, 10 days by
                          default).
- ``interview_thank_you`` Moved to Interview → send a thank-you within a day.
- ``offer_response``      Offer in hand → respond before it ages.
- ``reject_feedback``     Rejected → ask for feedback, turn a no into intel.

Idempotency is structural: every nudge has a deterministic ``dedupe_key``
and the repo refuses duplicates, so the scan can run hourly and retry
freely without ever double-nudging anyone.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta

from ..config import Settings
from ..models import Application, DraftType, Nudge, ScanReport, Status, utcnow
from ..repos.base import Repo
from .generation import generate_draft
from .llm import Intelligence


def _last_transition_to(app: Application, status: Status) -> datetime | None:
    for change in reversed(app.status_history):
        if change.to_status == status:
            return change.at
    return None


def _follow_up_anchor(app: Application, existing_touches: list[Nudge]) -> datetime:
    """Cadence anchor: the user's last real activity, or the last touch."""
    anchor = app.last_activity_at
    for nudge in existing_touches:
        if nudge.created_at > anchor:
            anchor = nudge.created_at
    return anchor


def scan_user(
    repo: Repo,
    intelligence: Intelligence,
    settings: Settings,
    uid: str,
    now: datetime | None = None,
    generation_budget: int | None = None,
) -> ScanReport:
    now = now or utcnow()
    budget = settings.max_generated_per_scan if generation_budget is None else generation_budget
    report = ScanReport()
    all_nudges = repo.list_nudges(uid)

    for app in repo.list_applications(uid):
        report.scanned += 1
        app_nudges = [n for n in all_nudges if n.application_id == app.id]

        if app.status == Status.APPLIED:
            touches = sorted(
                (n for n in app_nudges if n.rule == "follow_up"), key=lambda n: n.touch
            )
            next_touch = len(touches) + 1
            backoff = settings.follow_up_backoff
            if next_touch <= len(backoff):
                due = _follow_up_anchor(app, touches) + timedelta(days=backoff[next_touch - 1])
                if now >= due:
                    quiet_days = (now - app.last_activity_at).days
                    nudge = Nudge(
                        uid=uid,
                        application_id=app.id,
                        rule="follow_up",
                        touch=next_touch,
                        headline=f"Follow up with {app.company or app.role}",
                        detail=(
                            f"{quiet_days} quiet days on your {app.role} application. "
                            f"Touch {next_touch} of {len(backoff)} in your cadence — a drafted "
                            "follow-up is attached. Review, personalize, send."
                        ),
                        due_at=due,
                        dedupe_key=f"{app.id}:follow_up:{next_touch}",
                    )
                    if repo.create_nudge_if_absent(nudge):
                        report.nudges_created += 1
                        if report.drafts_generated < budget:
                            draft = generate_draft(
                                repo,
                                intelligence,
                                app,
                                DraftType.FOLLOW_UP_EMAIL,
                                touch=next_touch,
                            )
                            nudge.draft_id = draft.id
                            repo.update_nudge(nudge)
                            report.drafts_generated += 1

        elif app.status == Status.INTERVIEW:
            moved_at = _last_transition_to(app, Status.INTERVIEW)
            if moved_at:
                due = moved_at + timedelta(days=settings.interview_thank_you_days)
                if now >= due:
                    nudge = Nudge(
                        uid=uid,
                        application_id=app.id,
                        rule="interview_thank_you",
                        headline=f"Send a thank-you note to {app.company or app.role}",
                        detail=(
                            "You're in the interview loop. A short, specific thank-you within "
                            "a day of each round keeps you memorable."
                        ),
                        due_at=due,
                        dedupe_key=f"{app.id}:interview_thank_you:{moved_at.date().isoformat()}",
                    )
                    if repo.create_nudge_if_absent(nudge):
                        report.nudges_created += 1

        elif app.status == Status.OFFER:
            moved_at = _last_transition_to(app, Status.OFFER)
            if moved_at:
                due = moved_at + timedelta(days=settings.offer_response_days)
                if now >= due:
                    nudge = Nudge(
                        uid=uid,
                        application_id=app.id,
                        rule="offer_response",
                        headline=f"Respond to the offer from {app.company or app.role}",
                        detail=(
                            "Offers age fast. Evaluate it, negotiate it, or accept it — "
                            "just don't leave it hanging."
                        ),
                        due_at=due,
                        dedupe_key=f"{app.id}:offer_response:{moved_at.date().isoformat()}",
                    )
                    if repo.create_nudge_if_absent(nudge):
                        report.nudges_created += 1

        elif app.status == Status.REJECT:
            moved_at = _last_transition_to(app, Status.REJECT)
            if moved_at:
                due = moved_at + timedelta(days=settings.reject_feedback_days)
                if now >= due:
                    nudge = Nudge(
                        uid=uid,
                        application_id=app.id,
                        rule="reject_feedback",
                        headline=f"Ask {app.company or app.role} for feedback",
                        detail=(
                            "A gracious two-line feedback request turns a rejection into "
                            "intel for your next application."
                        ),
                        due_at=due,
                        dedupe_key=f"{app.id}:reject_feedback:{moved_at.date().isoformat()}",
                    )
                    if repo.create_nudge_if_absent(nudge):
                        report.nudges_created += 1

    return report


def scan_all(
    repo: Repo,
    intelligence: Intelligence,
    settings: Settings,
    now: datetime | None = None,
) -> ScanReport:
    started = time.monotonic()
    total = ScanReport()
    for uid in repo.scan_users():
        result = scan_user(
            repo,
            intelligence,
            settings,
            uid,
            now=now,
            generation_budget=settings.max_generated_per_scan - total.drafts_generated,
        )
        total.scanned += result.scanned
        total.nudges_created += result.nudges_created
        total.drafts_generated += result.drafts_generated
    total.duration_ms = int((time.monotonic() - started) * 1000)
    return total
