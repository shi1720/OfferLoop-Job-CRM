"""Application CRUD + the persistent state machine."""

from __future__ import annotations


class TestCrud:
    def test_create_and_list(self, client):
        created = client.post(
            "/api/applications",
            json={"role": "Senior Backend Engineer", "company": "Finlo", "location": "Bengaluru"},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["status"] == "applied"
        assert body["status_history"][0]["to_status"] == "applied"

        listed = client.get("/api/applications").json()
        assert len(listed) == 1

    def test_role_is_required(self, client):
        assert client.post("/api/applications", json={"company": "Finlo", "role": "  "}).status_code == 422

    def test_get_missing_is_404(self, client):
        assert client.get("/api/applications/nope").status_code == 404

    def test_delete_cascades_drafts(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer"}).json()["id"]
        client.post(f"/api/applications/{app_id}/drafts", json={"type": "cover_letter"})
        assert client.delete(f"/api/applications/{app_id}").status_code == 204
        assert client.get("/api/drafts").json() == []


class TestTransitions:
    def test_status_change_is_recorded_with_note(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer", "company": "Cartful"}).json()["id"]
        moved = client.patch(
            f"/api/applications/{app_id}",
            json={"status": "interview", "status_note": "Recruiter call went well"},
        ).json()
        assert moved["status"] == "interview"
        assert len(moved["status_history"]) == 2
        change = moved["status_history"][-1]
        assert change["from_status"] == "applied"
        assert change["to_status"] == "interview"
        assert change["note"] == "Recruiter call went well"

    def test_same_status_patch_adds_no_history(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer"}).json()["id"]
        patched = client.patch(f"/api/applications/{app_id}", json={"status": "applied"}).json()
        assert len(patched["status_history"]) == 1

    def test_full_journey_applied_to_offer(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer"}).json()["id"]
        for status in ("interview", "offer"):
            client.patch(f"/api/applications/{app_id}", json={"status": status})
        final = client.get(f"/api/applications/{app_id}").json()
        assert [c["to_status"] for c in final["status_history"]] == ["applied", "interview", "offer"]


class TestSystem:
    def test_health(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["mode"] == "demo"
        assert body["models"]["flash"] == "gemini-3.7-flash"

    def test_config_exposes_cadence_not_secrets(self, client):
        body = client.get("/api/config").json()
        assert body["cadence"]["follow_up_backoff_days"] == [5, 7, 10]
        assert "gemini" not in str(body).lower()

    def test_profile_roundtrip(self, client):
        updated = client.put("/api/profile", json={"name": "Shivam Gupta", "skills": ["Python"]}).json()
        assert updated["name"] == "Shivam Gupta"
        assert client.get("/api/profile").json()["skills"] == ["Python"]
