"""Regression tests for the adversarial-review findings: auth gates,
datetime coercion, duplicate ids, orphan adoption, and label normalization."""

from __future__ import annotations

from app.services.ingest import ingest_drafts, ingest_postings, run_import

POSTINGS = (
    b"id,from,to,type,description\n"
    b"1,2026-06-01,2026-06-30,full-time,Senior Backend Engineer - Python, Bengaluru\n"
)


class TestDemoAuth:
    def test_missing_token_is_401(self, client):
        del client.headers["Authorization"]
        assert client.get("/api/applications").status_code == 401

    def test_wrong_token_is_401(self, client):
        client.headers["Authorization"] = "Bearer wrong"
        assert client.get("/api/applications").status_code == 401

    def test_demo_token_is_accepted(self, client):
        assert client.get("/api/applications").status_code == 200


class TestNaiveDatetimes:
    def test_bare_date_payload_cannot_brick_the_board(self, client):
        created = client.post(
            "/api/applications",
            json={"role": "Engineer", "applied_at": "2026-08-15"},  # tz-naive
        )
        assert created.status_code == 201
        # These all compare datetimes internally — naive input used to 500 them.
        assert client.get("/api/applications").status_code == 200
        assert client.get("/api/analytics").status_code == 200
        assert client.post("/api/scan").status_code == 200
        app_id = created.json()["id"]
        assert client.post(f"/api/applications/{app_id}/drafts", json={"type": "cover_letter"}).status_code == 201


class TestDuplicateIds:
    def test_duplicate_id_within_one_file_updates_not_duplicates(self, repo, intelligence):
        data = (
            b"id,from,to,type,description\n"
            b"1,2026-06-01,2026-06-30,full-time,First version - Python\n"
            b"1,2026-06-02,2026-06-30,full-time,Second version - Go\n"
        )
        report = ingest_postings(repo, intelligence, "u1", data)
        assert report.accepted == 1
        assert report.updated == 1
        apps = repo.list_applications("u1")
        assert len(apps) == 1
        assert "Second version" in apps[0].description  # last row wins


class TestOrphanAdoption:
    def test_drafts_imported_before_their_posting_get_relinked(self, repo, intelligence):
        drafts = b'id,jobId,type,contents,status\n7,42,cover_letter,"Waiting for my posting",sent\n'
        report = run_import(repo, intelligence, "u1", drafts=(drafts, "d.csv"))
        assert report.orphaned_drafts == 1
        assert repo.get_draft_by_external_id("u1", "7").application_id == ""

        postings = b"id,from,to,type,description\n42,2026-06-01,2026-06-30,full-time,Backend Engineer - Python\n"
        second = run_import(repo, intelligence, "u1", postings=(postings, "p.csv"))
        assert second.relinked_drafts == 1
        adopted = repo.get_draft_by_external_id("u1", "7")
        parent = repo.get_application_by_external_id("u1", "42")
        assert adopted.application_id == parent.id


class TestLabelNormalization:
    def test_follow_dash_up_is_accepted(self, repo, intelligence):
        ingest_postings(repo, intelligence, "u1", POSTINGS)
        data = (
            b"id,jobId,type,contents,status\n"
            b"1,1,follow-up,Checking in,sent\n"
            b"2,1,Thank You,Thanks for the interview,draft\n"
        )
        report, linked, _, _ = ingest_drafts(repo, intelligence, "u1", data)
        assert report.accepted == 2
        assert linked == 2
        assert {d.type.value for d in repo.list_drafts("u1")} == {"follow_up_email"}

    def test_job_types_canonicalized(self, repo, intelligence):
        data = (
            b"id,from,to,type,description\n"
            b"1,2026-06-01,2026-06-30,Full Time,A - Python\n"
            b"2,2026-06-01,2026-06-30,fulltime,B - Python\n"
            b"3,2026-06-01,2026-06-30,intern,C - Python\n"
        )
        ingest_postings(repo, intelligence, "u1", data)
        types = {a.external_id: a.job_type for a in repo.list_applications("u1")}
        assert types == {"1": "full-time", "2": "full-time", "3": "internship"}

    def test_full_month_names_parse(self, repo, intelligence):
        data = (
            b"id,from,to,type,description\n"
            b"1,September 1 2026,30 September 2026,full-time,Backend Engineer - Python\n"
        )
        report = ingest_postings(repo, intelligence, "u1", data)
        assert report.accepted == 1
        assert repo.get_application_by_external_id("u1", "1").applied_at.date().isoformat() == "2026-09-01"


class TestReimportEmbeddingFreshness:
    def test_changed_contents_drop_stale_embedding(self, repo, intelligence):
        ingest_postings(repo, intelligence, "u1", POSTINGS)
        first = b'id,jobId,type,contents,status\n1,1,cover_letter,"Version one",draft\n'
        ingest_drafts(repo, intelligence, "u1", first)
        draft = repo.get_draft_by_external_id("u1", "1")
        draft.embedding = [0.1, 0.2]  # simulate a live-mode embedding
        repo.put_draft(draft)

        second = b'id,jobId,type,contents,status\n1,1,cover_letter,"Version two, rewritten",draft\n'
        ingest_drafts(repo, intelligence, "u1", second)
        assert repo.get_draft_by_external_id("u1", "1").embedding is None


class TestFirebaseAuthProxy:
    @staticmethod
    def _has_proxy_route(app) -> bool:
        return any(getattr(route, "path", "") == "/__/{path:path}" for route in app.routes)

    def test_absent_without_project(self, client):
        assert not self._has_proxy_route(client.app)

    def test_registered_when_project_configured(self):
        from app.config import Settings
        from app.main import create_app

        app = create_app(Settings(app_mode="demo", demo_seed=False, gcp_project="proj", _env_file=None))
        assert self._has_proxy_route(app)

    def test_proxy_route_actually_parses_requests(self, monkeypatch):
        # Regression: with deferred annotations, a Request type imported
        # inside the factory made FastAPI demand a `request` QUERY param
        # (422 on every call). Call the route for real, with httpx stubbed.
        import httpx
        from fastapi.testclient import TestClient

        from app.config import Settings
        from app.main import create_app

        class FakeResponse:
            content = b"<html>auth helper</html>"
            status_code = 200
            headers = {"content-type": "text/html", "x-upstream": "strip-me"}

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs): ...
            async def __aenter__(self):
                return self
            async def __aexit__(self, *exc):
                return False
            async def request(self, method, url, **kwargs):
                assert url.startswith("https://proj.firebaseapp.com/__/auth/handler")
                return FakeResponse()

        monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
        app = create_app(Settings(app_mode="demo", demo_seed=False, gcp_project="proj", _env_file=None))
        with TestClient(app) as client:
            response = client.get("/__/auth/handler?code=abc")
            assert response.status_code == 200
            assert b"auth helper" in response.content
            assert "x-upstream" not in response.headers
