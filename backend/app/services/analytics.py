"""Pipeline analytics — the numbers a sales team would demand of a funnel,
computed for a job search."""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from ..config import Settings
from ..models import Application, Draft, Nudge, NudgeStatus, Status, utcnow
from ..repos.base import Repo


class WeekActivity(BaseModel):
    week_start: str  # ISO date of the Monday
    applications: int = 0
    drafts: int = 0
    status_changes: int = 0


class AnalyticsSummary(BaseModel):
    total_applications: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    reached_interview: int = 0
    reached_offer: int = 0
    interview_rate: float = 0.0  # % of applications that reached interview
    offer_rate: float = 0.0  # % of interviews that reached offer
    median_days_to_interview: float | None = None
    ghosted: int = 0
    ghost_rate: float = 0.0
    drafts_total: int = 0
    drafts_sent: int = 0
    nudges_pending: int = 0
    nudges_actioned: int = 0
    weekly: list[WeekActivity] = Field(default_factory=list)


def _week_start(when: datetime) -> str:
    monday = when.date() - timedelta(days=when.weekday())
    return monday.isoformat()


def _reached(app: Application, status: Status) -> datetime | None:
    for change in app.status_history:
        if change.to_status == status:
            return change.at
    return app.applied_at if app.status == status and status == Status.APPLIED else None


def summarize(repo: Repo, settings: Settings, uid: str, now: datetime | None = None) -> AnalyticsSummary:
    now = now or utcnow()
    apps: list[Application] = repo.list_applications(uid)
    drafts: list[Draft] = repo.list_drafts(uid)
    nudges: list[Nudge] = repo.list_nudges(uid)

    summary = AnalyticsSummary(total_applications=len(apps))
    summary.by_status = {status.value: 0 for status in Status}
    days_to_interview: list[float] = []
    ghost_cutoff = now - timedelta(days=settings.ghost_after_days)

    for app in apps:
        summary.by_status[app.status.value] += 1
        interview_at = _reached(app, Status.INTERVIEW)
        if interview_at:
            summary.reached_interview += 1
            days_to_interview.append(max(0.0, (interview_at - app.applied_at).total_seconds() / 86400))
        if _reached(app, Status.OFFER):
            summary.reached_offer += 1
        if app.status == Status.APPLIED and app.last_activity_at < ghost_cutoff:
            summary.ghosted += 1

    if apps:
        summary.interview_rate = round(100 * summary.reached_interview / len(apps), 1)
        applied_count = summary.by_status[Status.APPLIED.value]
        summary.ghost_rate = round(100 * summary.ghosted / applied_count, 1) if applied_count else 0.0
    if summary.reached_interview:
        summary.offer_rate = round(100 * summary.reached_offer / summary.reached_interview, 1)
    if days_to_interview:
        summary.median_days_to_interview = round(statistics.median(days_to_interview), 1)

    summary.drafts_total = len(drafts)
    summary.drafts_sent = sum(1 for d in drafts if d.status.value == "sent")
    summary.nudges_pending = sum(1 for n in nudges if n.status == NudgeStatus.PENDING)
    summary.nudges_actioned = sum(1 for n in nudges if n.status == NudgeStatus.DONE)

    # last 8 weeks of activity, oldest first
    weeks: dict[str, WeekActivity] = {}
    for offset in range(7, -1, -1):
        start = _week_start(now - timedelta(weeks=offset))
        weeks[start] = WeekActivity(week_start=start)
    for app in apps:
        key = _week_start(app.created_at)
        if key in weeks:
            weeks[key].applications += 1
        for change in app.status_history:
            key = _week_start(change.at)
            if key in weeks and change.from_status is not None:
                weeks[key].status_changes += 1
    for draft in drafts:
        key = _week_start(draft.created_at)
        if key in weeks:
            weeks[key].drafts += 1
    summary.weekly = list(weeks.values())
    return summary
