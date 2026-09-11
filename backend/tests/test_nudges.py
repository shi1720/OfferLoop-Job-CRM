"""Cadence engine: right nudge, right time, exactly once."""

from __future__ import annotations

from datetime import timedelta

from app.models import Status, StatusChange, utcnow
from app.services.nudges import scan_user
from tests.conftest import make_application

NOW = utcnow()


def _aged(repo, days: int, **overrides):
    applied = NOW - timedelta(days=days)
    app = make_application(applied_at=applied, last_activity_at=applied, **overrides)
    app.status_history = [StatusChange(to_status=Status.APPLIED, at=applied)]
    repo.put_application(app)
    return app


def _moved(repo, app, status: Status, days_ago: int):
    at = NOW - timedelta(days=days_ago)
    app.status_history.append(StatusChange(from_status=app.status, to_status=status, at=at))
    app.status = status
    app.last_activity_at = at
    repo.put_application(app)
    return app


class TestFollowUpCadence:
    def test_quiet_application_gets_nudge_with_draft(self, repo, intelligence, settings):
        app = _aged(repo, days=6)
        report = scan_user(repo, intelligence, settings, "u1", now=NOW)
        assert report.nudges_created == 1
        assert report.drafts_generated == 1
        nudge = repo.list_nudges("u1")[0]
        assert nudge.rule == "follow_up"
        assert nudge.touch == 1
        draft = repo.get_draft("u1", nudge.draft_id)
        assert draft.type.value == "follow_up_email"
        assert draft.application_id == app.id

    def test_fresh_application_is_left_alone(self, repo, intelligence, settings):
        _aged(repo, days=3)
        report = scan_user(repo, intelligence, settings, "u1", now=NOW)
        assert report.nudges_created == 0

    def test_scan_is_idempotent(self, repo, intelligence, settings):
        _aged(repo, days=6)
        scan_user(repo, intelligence, settings, "u1", now=NOW)
        second = scan_user(repo, intelligence, settings, "u1", now=NOW)
        assert second.nudges_created == 0
        assert len(repo.list_nudges("u1")) == 1

    def test_backoff_spaces_the_touches(self, repo, intelligence, settings):
        _aged(repo, days=6)
        scan_user(repo, intelligence, settings, "u1", now=NOW)
        # 6 days later: touch 1 was created "now" during the first scan, and
        # touch 2 needs 7 more quiet days after it — not due yet.
        mid = scan_user(repo, intelligence, settings, "u1", now=NOW + timedelta(days=6))
        assert mid.nudges_created == 0
        late = scan_user(repo, intelligence, settings, "u1", now=NOW + timedelta(days=8))
        assert late.nudges_created == 1
        touches = sorted(n.touch for n in repo.list_nudges("u1"))
        assert touches == [1, 2]

    def test_cadence_stops_after_max_touches(self, repo, intelligence, settings):
        _aged(repo, days=6)
        when = NOW
        for _ in range(6):  # far more scans than touches
            scan_user(repo, intelligence, settings, "u1", now=when)
            when += timedelta(days=30)
        assert len(repo.list_nudges("u1")) == len(settings.follow_up_backoff)

    def test_autodraft_does_not_reset_staleness_clock(self, repo, intelligence, settings):
        app = _aged(repo, days=6)
        before = repo.get_application("u1", app.id).last_activity_at
        scan_user(repo, intelligence, settings, "u1", now=NOW)
        after = repo.get_application("u1", app.id).last_activity_at
        assert after == before

    def test_generation_budget_caps_llm_spend(self, repo, intelligence, settings):
        for i in range(5):
            _aged(repo, days=6, role=f"Role {i}")
        report = scan_user(repo, intelligence, settings, "u1", now=NOW, generation_budget=2)
        assert report.nudges_created == 5
        assert report.drafts_generated == 2


class TestStageRules:
    def test_interview_thank_you(self, repo, intelligence, settings):
        app = _aged(repo, days=10)
        _moved(repo, app, Status.INTERVIEW, days_ago=2)
        report = scan_user(repo, intelligence, settings, "u1", now=NOW)
        rules = {n.rule for n in repo.list_nudges("u1")}
        assert rules == {"interview_thank_you"}
        assert report.nudges_created == 1

    def test_offer_response(self, repo, intelligence, settings):
        app = _aged(repo, days=20)
        _moved(repo, app, Status.OFFER, days_ago=4)
        scan_user(repo, intelligence, settings, "u1", now=NOW)
        assert {n.rule for n in repo.list_nudges("u1")} == {"offer_response"}

    def test_reject_feedback(self, repo, intelligence, settings):
        app = _aged(repo, days=20)
        _moved(repo, app, Status.REJECT, days_ago=3)
        scan_user(repo, intelligence, settings, "u1", now=NOW)
        assert {n.rule for n in repo.list_nudges("u1")} == {"reject_feedback"}

    def test_recent_transition_not_yet_due(self, repo, intelligence, settings):
        app = _aged(repo, days=20)
        _moved(repo, app, Status.OFFER, days_ago=1)
        report = scan_user(repo, intelligence, settings, "u1", now=NOW)
        assert report.nudges_created == 0


class TestNudgeApi:
    def test_scan_and_inbox_lifecycle(self, client):
        client.post("/api/applications", json={"role": "Backend Engineer", "company": "Finlo"})
        # backdate by direct repo access (API has no time machine)
        repo = client.app_state.repo
        app = repo.list_applications("demo-user")[0]
        app.applied_at = app.last_activity_at = utcnow() - timedelta(days=6)
        repo.put_application(app)

        scan = client.post("/api/scan").json()
        assert scan["nudges_created"] == 1

        nudges = client.get("/api/nudges?status=pending").json()
        assert len(nudges) == 1
        nudge_id = nudges[0]["id"]

        done = client.post(f"/api/nudges/{nudge_id}/done")
        assert done.status_code == 200
        assert client.get("/api/nudges?status=pending").json() == []

    def test_scheduler_endpoint_open_in_demo_mode(self, client):
        response = client.post("/api/tasks/nudge-scan")
        assert response.status_code == 200
        assert "nudges_created" in response.json()
