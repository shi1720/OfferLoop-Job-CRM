"""The demo seed dogfoods the import pipeline — verify the whole boot."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def seeded_client():
    app = create_app(Settings(app_mode="demo", demo_seed=True, _env_file=None))
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer demo"
        yield client


class TestDemoSeed:
    def test_boot_ingests_sample_datasets(self, seeded_client):
        apps = seeded_client.get("/api/applications").json()
        assert len(apps) == 12
        statuses = {a["status"] for a in apps}
        assert {"applied", "interview", "offer", "reject"} <= statuses

    def test_drafts_linked_and_nudges_live(self, seeded_client):
        drafts = seeded_client.get("/api/drafts").json()
        assert len(drafts) >= 16  # imported + scan-generated follow-ups
        nudges = seeded_client.get("/api/nudges?status=pending").json()
        assert len(nudges) >= 4
        rules = {n["rule"] for n in nudges}
        assert "follow_up" in rules
        assert "interview_thank_you" in rules

    def test_import_report_recorded(self, seeded_client):
        history = seeded_client.get("/api/import/history").json()
        assert history
        assert history[0]["postings"]["accepted"] == 12
        assert history[0]["linked_drafts"] == 14
        assert history[0]["orphaned_drafts"] == 2
