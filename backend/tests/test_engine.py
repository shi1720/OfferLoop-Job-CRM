"""Bring-your-own-key engine: encryption, selection, allowance, momentum."""

from __future__ import annotations

from datetime import timedelta

from app.auth import DEMO_UID
from app.config import Settings
from app.models import Profile, Status, StatusChange, utcnow
from app.services import engine
from app.services.llm import GeminiError, TemplateIntelligence
from app.services.nudges import scan_user
from tests.conftest import make_application

NOW = utcnow()


def live_settings(**overrides) -> Settings:
    """A live-mode Settings object for unit-testing engine selection.

    Never used to build an app (that would need Firestore) — engine
    selection only reads config fields, so this stays hermetic.
    """
    defaults = dict(
        app_mode="live",
        demo_seed=False,
        gemini_api_key="server-key-for-tests",
        key_secret="unit-test-secret",
        _env_file=None,
    )
    defaults.update(overrides)
    return Settings(**defaults)


class TestKeyStorage:
    def test_encrypt_roundtrip_with_secret(self):
        settings = live_settings()
        stored = engine.encrypt_key(settings, "AIzaSyFakeUserKey123456789")
        assert stored.startswith("enc:")
        assert "AIzaSy" not in stored  # ciphertext, not plaintext
        assert engine.decrypt_key(settings, stored) == "AIzaSyFakeUserKey123456789"

    def test_plaintext_fallback_without_secret(self):
        settings = live_settings(key_secret="")
        stored = engine.encrypt_key(settings, "AIzaSyFakeUserKey123456789")
        assert stored.startswith("raw:")
        assert engine.decrypt_key(settings, stored) == "AIzaSyFakeUserKey123456789"

    def test_rotated_secret_reads_as_no_key(self):
        stored = engine.encrypt_key(live_settings(key_secret="old"), "AIzaSyFakeUserKey123456789")
        assert engine.decrypt_key(live_settings(key_secret="new"), stored) is None

    def test_decrypt_empty_and_garbage(self):
        settings = live_settings()
        assert engine.decrypt_key(settings, "") is None
        assert engine.decrypt_key(settings, "enc:not-real-ciphertext") is None

    def test_mask_never_reveals_more_than_tail(self):
        assert engine.mask_key("AIzaSyFakeUserKey1a2b") == "•••• 1a2b"
        assert engine.mask_key("short") == "••••"


class TestEngineSelection:
    def test_demo_mode_wins(self):
        settings = Settings(app_mode="demo", demo_seed=False, _env_file=None)
        profile = Profile(uid="u1")
        assert engine.engine_source(settings, TemplateIntelligence(), profile) == engine.DEMO

    def test_user_key_beats_free_credits(self):
        settings = live_settings()
        profile = Profile(uid="u1", gemini_api_key_enc=engine.encrypt_key(settings, "AIzaSyUserOwnKey12345678"))
        assert engine.engine_source(settings, TemplateIntelligence(), profile) == engine.YOUR_KEY

    def test_free_credits_while_allowance_lasts(self):
        settings = live_settings(free_generations=3)
        server = TemplateIntelligence()
        profile = Profile(uid="u1", free_used=2)
        chosen, source = engine.engine_for(settings, server, profile)
        assert source == engine.FREE_CREDITS
        assert chosen is server  # free drafts run on the server's engine

    def test_key_required_once_allowance_spent(self):
        settings = live_settings(free_generations=3)
        profile = Profile(uid="u1", free_used=3)
        chosen, source = engine.engine_for(settings, TemplateIntelligence(), profile)
        assert source == engine.KEY_REQUIRED
        # degradable callers (extraction/embeddings) still get a working engine
        assert isinstance(chosen, TemplateIntelligence)

    def test_no_server_key_means_key_required_from_day_one(self):
        settings = live_settings(gemini_api_key="")
        profile = Profile(uid="u1", free_used=0)
        _, source = engine.engine_for(settings, TemplateIntelligence(), profile)
        assert source == engine.KEY_REQUIRED


class TestMomentum:
    def test_levels(self):
        assert engine.level_for(0) == "Starter"
        assert engine.level_for(99) == "Starter"
        assert engine.level_for(100) == "Consistent"
        assert engine.level_for(300) == "Relentless"
        assert engine.level_for(750) == "Closer"
        assert engine.level_for(5000) == "Legend"

    def test_award_persists_points(self, repo):
        profile = Profile(uid="u1")
        engine.award(repo, profile, "application_logged")
        engine.award(repo, profile, "reached_offer")
        assert repo.get_profile("u1").points == 110

    def test_unknown_event_is_a_noop(self, repo):
        profile = Profile(uid="u1")
        engine.award(repo, profile, "made_coffee")
        assert repo.get_profile("u1") is None  # nothing written


class TestPublicProfile:
    def test_never_returns_raw_key(self):
        settings = live_settings()
        raw = "AIzaSyUserOwnKey12345678"
        profile = Profile(uid="u1", gemini_api_key_enc=engine.encrypt_key(settings, raw))
        public = engine.public_profile(settings, TemplateIntelligence(), profile)
        assert raw not in public.model_dump_json()
        assert public.gemini_key_masked == "•••• 5678"
        assert public.engine == engine.YOUR_KEY
        assert not hasattr(public, "gemini_api_key_enc")

    def test_free_remaining_floors_at_zero(self):
        settings = live_settings(free_generations=5)
        profile = Profile(uid="u1", free_used=9)
        public = engine.public_profile(settings, TemplateIntelligence(), profile)
        assert public.free_remaining == 0
        assert public.engine == engine.KEY_REQUIRED


class TestKeyEndpoints:
    def test_short_key_rejected_without_network_call(self, client):
        res = client.put("/api/profile/gemini-key", json={"key": "abc123"})
        assert res.status_code == 400
        assert res.json()["detail"]["code"] == "key_invalid"

    def test_invalid_key_rejected_with_reason(self, client, monkeypatch):
        monkeypatch.setattr(engine, "validate_gemini_key", lambda s, k: (False, "rejected by Gemini"))
        res = client.put("/api/profile/gemini-key", json={"key": "AIzaSyDefinitelyLongEnough123"})
        assert res.status_code == 400
        assert res.json()["detail"] == {"code": "key_invalid", "message": "rejected by Gemini"}

    def test_valid_key_stored_encrypted_and_masked(self, client, monkeypatch):
        monkeypatch.setattr(engine, "validate_gemini_key", lambda s, k: (True, "ok"))
        res = client.put("/api/profile/gemini-key", json={"key": "AIzaSyDefinitelyLongEnough123"})
        assert res.status_code == 200
        assert res.json()["gemini_key_masked"] == "•••• h123"
        assert "AIzaSy" not in res.text  # raw key never echoed back
        stored = client.app_state.repo.get_profile(DEMO_UID).gemini_api_key_enc
        assert stored and "AIzaSy" not in stored or stored.startswith("raw:")

    def test_remove_key(self, client, monkeypatch):
        monkeypatch.setattr(engine, "validate_gemini_key", lambda s, k: (True, "ok"))
        client.put("/api/profile/gemini-key", json={"key": "AIzaSyDefinitelyLongEnough123"})
        res = client.delete("/api/profile/gemini-key")
        assert res.status_code == 200
        assert res.json()["gemini_key_masked"] is None

    def test_profile_reports_points_and_level(self, client):
        client.post("/api/applications", json={"role": "Engineer", "company": "Finlo"})
        profile = client.get("/api/profile").json()
        assert profile["points"] == 10
        assert profile["level"] == "Starter"


class TestGenerationGating:
    def test_402_when_key_required(self, client, monkeypatch):
        app_id = client.post("/api/applications", json={"role": "Engineer", "company": "Finlo"}).json()["id"]
        monkeypatch.setattr(
            engine, "engine_for", lambda s, i, p: (TemplateIntelligence(), engine.KEY_REQUIRED)
        )
        res = client.post(f"/api/applications/{app_id}/drafts", json={"type": "cover_letter"})
        assert res.status_code == 402
        assert res.json()["detail"]["code"] == "key_required"
        assert "Gemini API key" in res.json()["detail"]["message"]

    def test_free_credit_consumed_on_success(self, client, monkeypatch):
        app_id = client.post("/api/applications", json={"role": "Engineer", "company": "Finlo"}).json()["id"]
        monkeypatch.setattr(
            engine, "engine_for", lambda s, i, p: (TemplateIntelligence(), engine.FREE_CREDITS)
        )
        res = client.post(f"/api/applications/{app_id}/drafts", json={"type": "cover_letter"})
        assert res.status_code == 201
        assert client.app_state.repo.get_profile(DEMO_UID).free_used == 1

    def test_gemini_errors_map_to_http(self, client, monkeypatch):
        app_id = client.post("/api/applications", json={"role": "Engineer", "company": "Finlo"}).json()["id"]
        monkeypatch.setattr(
            engine, "engine_for", lambda s, i, p: (TemplateIntelligence(), engine.YOUR_KEY)
        )

        cases = {"key_invalid": 400, "quota_exhausted": 429, "timeout": 504, "unavailable": 502}
        for code, status in cases.items():

            def boom(*args, _code=code, **kwargs):
                raise GeminiError(_code, "synthetic failure")

            monkeypatch.setattr("app.routers.drafts.generate_draft", boom)
            res = client.post(f"/api/applications/{app_id}/drafts", json={"type": "cover_letter"})
            assert res.status_code == status, code
            assert res.json()["detail"]["code"] == f"gemini_{code}"
            assert res.json()["detail"]["message"]  # human-readable, non-empty

    def test_unknown_gemini_code_degrades_to_502(self, client, monkeypatch):
        app_id = client.post("/api/applications", json={"role": "Engineer", "company": "Finlo"}).json()["id"]
        monkeypatch.setattr(
            engine, "engine_for", lambda s, i, p: (TemplateIntelligence(), engine.YOUR_KEY)
        )

        def boom(*args, **kwargs):
            raise GeminiError("solar_flare", "a code the mapping has never heard of")

        monkeypatch.setattr("app.routers.drafts.generate_draft", boom)
        res = client.post(f"/api/applications/{app_id}/drafts", json={"type": "cover_letter"})
        assert res.status_code == 502  # never a bare 500
        assert res.json()["detail"]["code"] == "gemini_solar_flare"
        assert res.json()["detail"]["message"]

    def test_failed_generation_never_burns_a_credit(self, client, monkeypatch):
        app_id = client.post("/api/applications", json={"role": "Engineer", "company": "Finlo"}).json()["id"]
        monkeypatch.setattr(
            engine, "engine_for", lambda s, i, p: (TemplateIntelligence(), engine.FREE_CREDITS)
        )

        def boom(*args, **kwargs):
            raise GeminiError("timeout", "synthetic failure")

        monkeypatch.setattr("app.routers.drafts.generate_draft", boom)
        client.post(f"/api/applications/{app_id}/drafts", json={"type": "cover_letter"})
        profile = client.app_state.repo.get_profile(DEMO_UID)
        assert profile is None or profile.free_used == 0


class TestMomentumAwardsViaApi:
    def _points(self, client) -> int:
        return client.get("/api/profile").json()["points"]

    def test_log_and_send_and_nudge(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer", "company": "Finlo"}).json()["id"]
        assert self._points(client) == 10  # application_logged

        draft = client.post(f"/api/applications/{app_id}/drafts", json={"type": "follow_up_email"}).json()
        client.patch(f"/api/drafts/{draft['id']}", json={"status": "sent"})
        assert self._points(client) == 25  # +15 draft_sent

    def test_interview_and_offer_award_once(self, client):
        app_id = client.post("/api/applications", json={"role": "Engineer", "company": "Finlo"}).json()["id"]
        client.patch(f"/api/applications/{app_id}", json={"status": "interview"})
        assert self._points(client) == 40  # +30 first interview

        # bounce out and back — no farming the transition
        client.patch(f"/api/applications/{app_id}", json={"status": "applied"})
        client.patch(f"/api/applications/{app_id}", json={"status": "interview"})
        assert self._points(client) == 40

        client.patch(f"/api/applications/{app_id}", json={"status": "offer"})
        assert self._points(client) == 140  # +100 first offer


class TestScanRespectsAllowance:
    def _quiet_app(self, repo, uid="u1"):
        applied = NOW - timedelta(days=6)
        app = make_application(uid=uid, applied_at=applied, last_activity_at=applied)
        app.status_history = [StatusChange(to_status=Status.APPLIED, at=applied)]
        repo.put_application(app)
        return app

    def test_free_scan_draft_counts_against_allowance(self, repo, intelligence):
        settings = live_settings(free_generations=5)
        self._quiet_app(repo)
        report = scan_user(repo, intelligence, settings, "u1", now=NOW)
        assert report.nudges_created == 1
        assert report.drafts_generated == 1
        assert repo.get_profile("u1").free_used == 1

    def test_exhausted_allowance_still_nudges_without_draft(self, repo, intelligence):
        settings = live_settings(free_generations=5)
        repo.put_profile(Profile(uid="u1", free_used=5))
        self._quiet_app(repo)
        report = scan_user(repo, intelligence, settings, "u1", now=NOW)
        assert report.nudges_created == 1
        assert report.drafts_generated == 0  # nudge stands, draft politely absent

    def test_gemini_failure_never_kills_a_scan(self, repo, intelligence, settings, monkeypatch):
        self._quiet_app(repo)

        def boom(*args, **kwargs):
            raise GeminiError("quota_exhausted", "synthetic failure")

        monkeypatch.setattr("app.services.nudges.generate_draft", boom)
        report = scan_user(repo, intelligence, settings, "u1", now=NOW)
        assert report.nudges_created == 1  # the nudge is the product; the draft is a bonus
        assert report.drafts_generated == 0
