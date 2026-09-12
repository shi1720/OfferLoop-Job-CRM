"""Paste-a-link capture, contacts, prep packs, soft delete/undo, exports,
account deletion, tracker imports, push tokens, and the follow-up insight."""

from __future__ import annotations

from datetime import timedelta

from app.auth import DEMO_UID
from app.models import Draft, DraftStatus, DraftType, Nudge, Profile, Status, StatusChange, utcnow
from app.services import push
from app.services.analytics import summarize
from app.services.capture import CaptureError, capture_posting, strip_html
from app.services.llm import TemplateIntelligence
from app.services.nudges import scan_all, scan_user
from tests.conftest import make_application

JD_TEXT = (
    "Senior Backend Engineer at Finlo - Python, FastAPI, Bengaluru. "
    "We are looking for a full-time engineer to own our payments platform, "
    "work with PostgreSQL and Kafka, and ship reliably at scale."
)


class TestCapture:
    def test_text_mode_extracts_fields(self, client):
        res = client.post("/api/applications/capture", json={"text": JD_TEXT})
        assert res.status_code == 200
        data = res.json()
        assert "Senior Backend Engineer" in data["role"]
        assert data["company"] == "Finlo"
        assert data["job_type"] == "full-time"
        assert data["description"].startswith("Senior Backend Engineer")
        assert data["posting_url"] == ""

    def test_empty_and_too_short_are_422(self, client):
        assert client.post("/api/applications/capture", json={}).status_code == 422
        res = client.post("/api/applications/capture", json={"text": "too short"})
        assert res.status_code == 422
        assert "paste" in res.json()["detail"].lower()

    def test_ssrf_targets_are_refused(self, client):
        for url in (
            "http://169.254.169.254/computeMetadata/v1/",
            "http://127.0.0.1:8000/api/health",
            "http://localhost/admin",
            "ftp://example.com/jobs",
        ):
            res = client.post("/api/applications/capture", json={"url": url})
            assert res.status_code == 422, url

    def test_url_mode_uses_fetched_page(self, client, monkeypatch):
        html = f"<html><title>Platform Engineer | LinkedIn</title><body><p>{JD_TEXT}</p></body></html>"
        monkeypatch.setattr(
            "app.services.capture._fetch", lambda url: (html, "https://example.com/job/1")
        )
        res = client.post("/api/applications/capture", json={"url": "https://example.com/job/1"})
        assert res.status_code == 200
        assert res.json()["posting_url"] == "https://example.com/job/1"
        assert res.json()["company"] == "Finlo"

    def test_strip_html_removes_scripts_and_keeps_title(self):
        title, text = strip_html(
            "<title>Role — Naukri.com</title><script>evil()</script><p>Hello&amp;bye</p><li>x</li>"
        )
        assert title == "Role — Naukri.com"
        assert "evil" not in text
        assert "Hello&bye" in text

    def test_redirect_into_private_network_is_refused(self, intelligence, monkeypatch):
        """Auto-following a redirect would GET the metadata service before any
        final-URL check — every hop must be validated BEFORE it's requested."""
        import httpx

        requested: list[str] = []

        class FakeResponse:
            status_code = 302
            headers = {"location": "http://169.254.169.254/computeMetadata/v1/"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def stream(self, method, url):
                requested.append(url)
                return FakeResponse()

        monkeypatch.setattr(httpx, "Client", FakeClient)
        try:
            capture_posting(intelligence, url="http://8.8.8.8/job/1")
            raise AssertionError("expected CaptureError")
        except CaptureError as exc:
            assert "private network" in str(exc)
        # the public first hop was fetched; the private hop never was
        assert requested == ["http://8.8.8.8/job/1"]

    def test_thin_page_asks_for_paste(self, intelligence, monkeypatch):
        monkeypatch.setattr("app.services.capture._fetch", lambda url: ("<html>login</html>", url))
        try:
            capture_posting(intelligence, url="https://example.com/x")
            raise AssertionError("expected CaptureError")
        except CaptureError as exc:
            assert "Paste the job description" in str(exc)


class TestContactsAndInterview:
    def test_contact_and_url_roundtrip(self, client):
        created = client.post(
            "/api/applications",
            json={
                "role": "Engineer",
                "company": "Finlo",
                "contact_name": "Priya Sharma",
                "contact_email": "priya@finlo.dev",
                "posting_url": "https://finlo.dev/jobs/1",
            },
        ).json()
        assert created["contact_name"] == "Priya Sharma"
        patched = client.patch(
            f"/api/applications/{created['id']}", json={"contact_email": "talent@finlo.dev"}
        ).json()
        assert patched["contact_email"] == "talent@finlo.dev"
        assert patched["posting_url"] == "https://finlo.dev/jobs/1"

    def test_interview_at_set_and_clear(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer"}).json()["id"]
        when = "2026-10-01T09:30:00Z"
        patched = client.patch(f"/api/applications/{app_id}", json={"interview_at": when}).json()
        assert patched["interview_at"].startswith("2026-10-01T09:30")
        cleared = client.patch(f"/api/applications/{app_id}", json={"clear_interview": True}).json()
        assert cleared["interview_at"] is None


class TestSoftDeleteUndo:
    def test_delete_hides_and_restore_brings_everything_back(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer", "company": "Finlo"}).json()["id"]
        client.post(f"/api/applications/{app_id}/drafts", json={"type": "cover_letter"})

        assert client.delete(f"/api/applications/{app_id}").status_code == 204
        assert client.get("/api/applications").json() == []
        assert client.get("/api/drafts").json() == []
        assert client.get(f"/api/applications/{app_id}").status_code == 404

        restored = client.post(f"/api/applications/{app_id}/restore")
        assert restored.status_code == 200
        assert len(client.get("/api/applications").json()) == 1
        assert len(client.get("/api/drafts").json()) == 1  # drafts survive the round trip

    def test_deleted_apps_nudges_are_hidden(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer"}).json()["id"]
        repo = client.app_state.repo
        repo.create_nudge_if_absent(
            Nudge(
                uid=DEMO_UID,
                application_id=app_id,
                rule="follow_up",
                headline="x",
                due_at=utcnow(),
                dedupe_key=f"{app_id}:t",
            )
        )
        assert len(client.get("/api/nudges").json()) == 1
        client.delete(f"/api/applications/{app_id}")
        assert client.get("/api/nudges").json() == []
        client.post(f"/api/applications/{app_id}/restore")
        assert len(client.get("/api/nudges").json()) == 1

    def test_scan_skips_deleted(self, repo, intelligence, settings):
        applied = utcnow() - timedelta(days=6)
        app = make_application(applied_at=applied, last_activity_at=applied)
        app.status_history = [StatusChange(to_status=Status.APPLIED, at=applied)]
        repo.put_application(app)
        repo.delete_application("u1", app.id)
        report = scan_user(repo, intelligence, settings, "u1")
        assert report.scanned == 0
        assert report.nudges_created == 0

    def test_double_delete_is_404(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer"}).json()["id"]
        client.delete(f"/api/applications/{app_id}")
        assert client.delete(f"/api/applications/{app_id}").status_code == 404


class TestExportsAndAccount:
    def test_export_applications_csv(self, client):
        client.post("/api/applications", json={"role": "Engineer", "company": "Finlo", "notes": "via referral"})
        res = client.get("/api/export/applications.csv")
        assert res.status_code == 200
        assert "text/csv" in res.headers["content-type"]
        assert "attachment" in res.headers["content-disposition"]
        assert "Finlo" in res.text and "status_history" in res.text

    def test_export_excludes_deleted(self, client):
        app_id = client.post("/api/applications", json={"role": "Ghost", "company": "Gone"}).json()["id"]
        client.delete(f"/api/applications/{app_id}")
        assert "Gone" not in client.get("/api/export/applications.csv").text

    def test_export_drafts_csv(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer"}).json()["id"]
        client.post(f"/api/applications/{app_id}/drafts", json={"type": "follow_up_email"})
        res = client.get("/api/export/drafts.csv")
        assert res.status_code == 200
        assert "follow_up_email" in res.text

    def test_delete_account_wipes_everything(self, client):
        client.post("/api/applications", json={"role": "Engineer"})
        assert client.get("/api/profile").json()["points"] == 10
        assert client.delete("/api/account").status_code == 204
        assert client.get("/api/applications").json() == []
        assert client.get("/api/profile").json()["points"] == 0


class TestPrepPack:
    def test_template_pack_shape_and_award(self, client):
        app_id = client.post(
            "/api/applications", json={"role": "Backend Engineer", "company": "Finlo"}
        ).json()["id"]
        res = client.post(f"/api/applications/{app_id}/prep")
        assert res.status_code == 200
        pack = res.json()
        assert len(pack["questions"]) >= 5
        assert all(q["how_to_answer"] for q in pack["questions"])
        assert len(pack["stories"]) >= 2
        assert len(pack["questions_to_ask"]) >= 3
        assert "Finlo" in str(pack["questions"])  # grounded on THIS application

        # +10 log, +15 first prep; regenerating never awards twice
        assert client.get("/api/profile").json()["points"] == 25
        client.post(f"/api/applications/{app_id}/prep")
        assert client.get("/api/profile").json()["points"] == 25

    def test_prep_respects_key_gate(self, client, monkeypatch):
        from app.services import engine

        app_id = client.post("/api/applications", json={"role": "Engineer"}).json()["id"]
        monkeypatch.setattr(
            engine, "engine_for", lambda s, i, p: (TemplateIntelligence(), engine.KEY_REQUIRED)
        )
        res = client.post(f"/api/applications/{app_id}/prep")
        assert res.status_code == 402
        assert res.json()["detail"]["code"] == "key_required"

    def test_prep_consumes_a_free_credit(self, client, monkeypatch):
        from app.services import engine

        app_id = client.post("/api/applications", json={"role": "Engineer"}).json()["id"]
        monkeypatch.setattr(
            engine, "engine_for", lambda s, i, p: (TemplateIntelligence(), engine.FREE_CREDITS)
        )
        client.post(f"/api/applications/{app_id}/prep")
        assert client.app_state.repo.get_profile(DEMO_UID).free_used == 1


class TestNewDraftTypes:
    def test_referral_request(self, client):
        app_id = client.post(
            "/api/applications",
            json={"role": "Engineer", "company": "Finlo", "contact_name": "Priya"},
        ).json()["id"]
        res = client.post(f"/api/applications/{app_id}/drafts", json={"type": "referral_request"})
        assert res.status_code == 201
        draft = res.json()
        assert draft["type"] == "referral_request"
        assert draft["subject"].startswith("Referral request")
        assert "Priya" in draft["contents"] and "referral" in draft["contents"].lower()

    def test_linkedin_message_is_short_with_no_subject(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer", "company": "Finlo"}).json()["id"]
        res = client.post(f"/api/applications/{app_id}/drafts", json={"type": "linkedin_message"})
        assert res.status_code == 201
        draft = res.json()
        assert draft["subject"] == ""
        assert len(draft["contents"]) < 600


TEAL_CSV = b"""Company,Job Position,Location,URL,Status,Date Applied,Notes
Finlo,Senior Backend Engineer,Bengaluru,https://finlo.dev/j/1,Applied,2026-08-01,Referred by Priya
Cartful,Platform Engineer,Remote,https://cartful.io/j/2,Interviewing,2026-08-10,
Skylane,Data Engineer,Pune,https://skylane.in/j/3,Rejected,2026-07-15,Salary: 30LPA
Nimbus,Backend Developer,,,Bookmarked,,
"""

HUNTR_CSV = b"""Title,Company,List,Date Added,Job Post Url
SDE II,Brightpath,Offer,2026-08-20,https://bp.ai/j/9
Backend Engineer,Kettle,Wishlist,2026-09-01,
"""


class TestTrackerImports:
    def test_teal_export_maps_statuses(self, client):
        res = client.post("/api/import", files={"postings": ("teal.csv", TEAL_CSV, "text/csv")})
        assert res.status_code == 200
        assert res.json()["postings"]["accepted"] == 4
        apps = {a["role"]: a for a in client.get("/api/applications").json()}
        assert apps["Senior Backend Engineer"]["status"] == "applied"
        assert apps["Platform Engineer"]["status"] == "interview"
        assert apps["Data Engineer"]["status"] == "reject"
        assert apps["Backend Developer"]["status"] == "applied"  # bookmarked → applied
        assert apps["Senior Backend Engineer"]["posting_url"] == "https://finlo.dev/j/1"
        assert "Salary: 30LPA" in apps["Data Engineer"]["notes"]
        # a mapped stage beyond applied still records the journey
        history = [c["to_status"] for c in apps["Platform Engineer"]["status_history"]]
        assert history == ["applied", "interview"]

    def test_teal_reimport_updates_not_duplicates(self, client):
        client.post("/api/import", files={"postings": ("teal.csv", TEAL_CSV, "text/csv")})
        res = client.post("/api/import", files={"postings": ("teal.csv", TEAL_CSV, "text/csv")})
        assert res.json()["postings"]["updated"] == 4
        assert res.json()["postings"]["accepted"] == 0
        assert len(client.get("/api/applications").json()) == 4

    def test_huntr_export_shape(self, client):
        res = client.post("/api/import", files={"postings": ("huntr.csv", HUNTR_CSV, "text/csv")})
        assert res.json()["postings"]["accepted"] == 2
        apps = {a["role"]: a for a in client.get("/api/applications").json()}
        assert apps["SDE II"]["status"] == "offer"
        assert apps["Backend Engineer"]["status"] == "applied"

    def test_eval_schema_still_routes_to_postings(self, client):
        eval_csv = b"<id>,<from>,<to>,<type>,<description>\nJ1,2026-08-01,2026-09-01,full-time,Senior Backend Engineer at Finlo - Python, Bengaluru\n"
        res = client.post("/api/import", files={"postings": ("postings.csv", eval_csv, "text/csv")})
        assert res.json()["postings"]["accepted"] == 1
        app = client.get("/api/applications").json()[0]
        assert app["external_id"] == "J1"  # went through the postings pipeline


class TestPushTokens:
    def test_register_and_clear_via_api(self, client):
        res = client.put("/api/profile/push-token", json={"token": "tok-1"})
        assert res.json()["push_enabled"] is True
        client.put("/api/profile/push-token", json={"token": "tok-1"})  # dedupe
        assert client.app_state.repo.get_profile(DEMO_UID).push_tokens == ["tok-1"]
        res = client.delete("/api/profile/push-token")
        assert res.json()["push_enabled"] is False

    def test_token_cap(self, repo):
        profile = Profile(uid="u1")
        for i in range(8):
            profile = push.register_token(repo, profile, f"tok-{i}")
        assert len(profile.push_tokens) == push.MAX_TOKENS_PER_USER
        assert profile.push_tokens[-1] == "tok-7"

    def test_notify_prunes_dead_tokens(self, repo, monkeypatch):
        class UnregisteredError(Exception):
            pass

        sent: list[str] = []

        def fake_send(message):
            if message.token == "dead":
                raise UnregisteredError("gone")
            sent.append(message.token)

        import firebase_admin.messaging as messaging

        monkeypatch.setattr(messaging, "send", fake_send)
        profile = Profile(uid="u1", push_tokens=["dead", "alive"])
        repo.put_profile(profile)
        delivered = push.notify_nudges(repo, profile, 2, "https://offerloop.app")
        assert delivered == 1 and sent == ["alive"]
        assert repo.get_profile("u1").push_tokens == ["alive"]

    def test_scheduled_scan_invokes_notify(self, repo, intelligence, settings):
        applied = utcnow() - timedelta(days=6)
        app = make_application(applied_at=applied, last_activity_at=applied)
        app.status_history = [StatusChange(to_status=Status.APPLIED, at=applied)]
        repo.put_application(app)
        repo.put_profile(Profile(uid="u1", push_tokens=["tok"]))

        calls: list[tuple[str, int]] = []
        scan_all(
            repo,
            intelligence,
            settings,
            notify=lambda r, profile, count, link: calls.append((profile.uid, count)) or 1,
        )
        assert calls == [("u1", 1)]


class TestSentIsATransition:
    def test_resending_sent_never_farms_points_or_resets_clock(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer", "company": "Finlo"}).json()["id"]
        draft_id = client.post(f"/api/applications/{app_id}/drafts", json={"type": "follow_up_email"}).json()["id"]

        client.patch(f"/api/drafts/{draft_id}", json={"status": "sent"})
        points_after_send = client.get("/api/profile").json()["points"]
        clock_after_send = client.get(f"/api/applications/{app_id}").json()["last_activity_at"]

        # editing a sent draft while re-stating status: "sent" is not new outreach
        client.patch(f"/api/drafts/{draft_id}", json={"status": "sent", "contents": "tweaked"})
        assert client.get("/api/profile").json()["points"] == points_after_send
        assert client.get(f"/api/applications/{app_id}").json()["last_activity_at"] == clock_after_send


class TestFollowUpInsight:
    def _app_with_history(self, repo, uid, reached_interview: bool):
        app = make_application(uid=uid)
        if reached_interview:
            app.status_history.append(
                StatusChange(from_status=Status.APPLIED, to_status=Status.INTERVIEW, at=utcnow())
            )
            app.status = Status.INTERVIEW
        repo.put_application(app)
        return app

    def test_lift_computed_when_buckets_are_big_enough(self, repo, settings):
        # worked bucket: 3 apps with a sent follow-up, 2 reached interview
        for i in range(3):
            app = self._app_with_history(repo, "u1", reached_interview=i < 2)
            repo.put_draft(
                Draft(
                    uid="u1",
                    application_id=app.id,
                    type=DraftType.FOLLOW_UP_EMAIL,
                    contents="x",
                    status=DraftStatus.SENT,
                )
            )
        # silent bucket: 3 apps, 1 reached interview
        for i in range(3):
            self._app_with_history(repo, "u1", reached_interview=i < 1)

        summary = summarize(repo, settings, "u1")
        assert summary.followed_up == 3
        assert summary.followup_interview_rate == 66.7
        assert summary.no_followup_interview_rate == 33.3
        assert summary.followup_lift == 2.0

    def test_no_lift_on_thin_data(self, repo, settings):
        app = self._app_with_history(repo, "u1", reached_interview=True)
        repo.put_draft(
            Draft(uid="u1", application_id=app.id, type=DraftType.FOLLOW_UP_EMAIL, contents="x", status=DraftStatus.SENT)
        )
        summary = summarize(repo, settings, "u1")
        assert summary.followup_lift is None  # never fabricate significance


class TestWeeklyGoal:
    def test_weekly_goal_roundtrip(self, client):
        assert client.get("/api/profile").json()["weekly_goal"] == 5
        res = client.put("/api/profile", json={"weekly_goal": 12})
        assert res.json()["weekly_goal"] == 12
        assert client.put("/api/profile", json={"weekly_goal": -3}).status_code == 422
