"""Funnel math the way a sales leader would check it."""

from __future__ import annotations

from datetime import timedelta

from app.models import Status, StatusChange, utcnow
from app.services.analytics import summarize
from tests.conftest import make_application

NOW = utcnow()


def _app(repo, days_ago: int, journey: list[tuple[Status, int]] | None = None, **overrides):
    applied = NOW - timedelta(days=days_ago)
    app = make_application(applied_at=applied, last_activity_at=applied, created_at=applied, **overrides)
    app.status_history = [StatusChange(to_status=Status.APPLIED, at=applied)]
    for status, at_days_ago in journey or []:
        at = NOW - timedelta(days=at_days_ago)
        app.status_history.append(StatusChange(from_status=app.status, to_status=status, at=at))
        app.status = status
        app.last_activity_at = at
    repo.put_application(app)
    return app


class TestFunnel:
    def test_counts_rates_and_median(self, repo, settings):
        _app(repo, 30, [(Status.INTERVIEW, 20), (Status.OFFER, 5)])   # applied → interview in 10d
        _app(repo, 20, [(Status.INTERVIEW, 6)])                       # applied → interview in 14d
        _app(repo, 10)                                                # still applied
        _app(repo, 15, [(Status.REJECT, 8)])

        summary = summarize(repo, settings, "u1", now=NOW)
        assert summary.total_applications == 4
        assert summary.by_status == {"applied": 1, "interview": 1, "offer": 1, "reject": 1}
        assert summary.reached_interview == 2
        assert summary.reached_offer == 1
        assert summary.interview_rate == 50.0
        assert summary.offer_rate == 50.0
        assert summary.median_days_to_interview == 12.0

    def test_ghost_rate_counts_quiet_applied_only(self, repo, settings):
        _app(repo, 30)  # applied, quiet for 30d > 21d threshold → ghosted
        _app(repo, 5)   # applied, fresh
        _app(repo, 40, [(Status.REJECT, 2)])  # old but resolved — not a ghost

        summary = summarize(repo, settings, "u1", now=NOW)
        assert summary.ghosted == 1
        assert summary.ghost_rate == 50.0  # 1 of the 2 still-applied

    def test_weekly_buckets_cover_eight_weeks(self, repo, settings):
        _app(repo, 3)
        summary = summarize(repo, settings, "u1", now=NOW)
        assert len(summary.weekly) == 8
        assert sum(w.applications for w in summary.weekly) == 1

    def test_empty_pipeline_is_all_zeros(self, repo, settings):
        summary = summarize(repo, settings, "u1", now=NOW)
        assert summary.total_applications == 0
        assert summary.interview_rate == 0.0
        assert summary.median_days_to_interview is None


class TestAnalyticsApi:
    def test_endpoint_shape(self, client):
        client.post("/api/applications", json={"role": "Engineer"})
        body = client.get("/api/analytics").json()
        assert body["total_applications"] == 1
        assert "weekly" in body and len(body["weekly"]) == 8
