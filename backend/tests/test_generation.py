"""Generation must be grounded: history in, provenance out."""

from __future__ import annotations

from app.models import Draft, DraftStatus, DraftType, Profile
from app.services.generation import generate_draft
from tests.conftest import make_application


def _seed_history(repo, app, texts: list[str], kind=DraftType.COVER_LETTER, status=DraftStatus.SENT):
    for text in texts:
        other = make_application(role="Other role")
        repo.put_application(other)
        repo.put_draft(
            Draft(uid="u1", application_id=other.id, type=kind, contents=text, status=status)
        )


class TestGrounding:
    def test_generated_draft_records_provenance(self, repo, intelligence):
        app = make_application()
        repo.put_application(app)
        _seed_history(
            repo,
            app,
            ["Past letter about Python and FastAPI backends.", "Another letter about PostgreSQL work."],
        )
        draft = generate_draft(repo, intelligence, app, DraftType.COVER_LETTER)
        assert draft.source == "generated"
        assert len(draft.grounded_on) == 2  # both same-type drafts retrieved as exemplars
        assert all(repo.get_draft("u1", d) for d in draft.grounded_on)

    def test_cross_type_history_is_not_used(self, repo, intelligence):
        app = make_application()
        repo.put_application(app)
        _seed_history(repo, app, ["A follow up about Python."], kind=DraftType.FOLLOW_UP_EMAIL)
        draft = generate_draft(repo, intelligence, app, DraftType.COVER_LETTER)
        assert draft.grounded_on == []

    def test_contents_use_application_context(self, repo, intelligence):
        app = make_application(role="Data Platform Engineer", company="Nimbus Analytics")
        repo.put_application(app)
        repo.put_profile(Profile(uid="u1", name="Shivam Gupta", skills=["Python", "Kafka"]))
        draft = generate_draft(repo, intelligence, app, DraftType.FOLLOW_UP_EMAIL)
        assert "Data Platform Engineer" in draft.subject or "Data Platform Engineer" in draft.contents
        assert "Shivam Gupta" in draft.contents

    def test_generation_never_resets_staleness_clock(self, repo, intelligence):
        # Writing a draft is preparation, not outreach — only marking it
        # sent counts as activity (see drafts router).
        app = make_application()
        repo.put_application(app)
        before = repo.get_application("u1", app.id).last_activity_at
        generate_draft(repo, intelligence, app, DraftType.COVER_LETTER)
        assert repo.get_application("u1", app.id).last_activity_at == before


class TestDraftApi:
    def test_generate_edit_send_lifecycle(self, client):
        app_id = client.post(
            "/api/applications", json={"role": "Backend Engineer", "company": "Finlo"}
        ).json()["id"]

        draft = client.post(
            f"/api/applications/{app_id}/drafts", json={"type": "follow_up_email"}
        ).json()
        assert draft["type"] == "follow_up_email"
        assert draft["status"] == "draft"
        assert "embedding" not in draft

        edited = client.patch(
            f"/api/drafts/{draft['id']}", json={"contents": "My own words now."}
        ).json()
        assert edited["source"] == "edited"

        sent = client.patch(f"/api/drafts/{draft['id']}", json={"status": "sent"}).json()
        assert sent["status"] == "sent"

    def test_generate_for_missing_application_404s(self, client):
        assert client.post("/api/applications/nope/drafts", json={"type": "cover_letter"}).status_code == 404


class TestWritingRules:
    def test_style_rules_reach_the_prompt(self):
        from app.services.llm import DraftContext, _writer_prompt

        prompt = _writer_prompt(
            DraftContext(kind="cover_letter", role="PM", company="Finlo", style_rules="Never use em dashes.")
        )
        assert "HARD WRITING RULES" in prompt
        assert "Never use em dashes." in prompt

    def test_rules_absent_when_unset(self):
        from app.services.llm import DraftContext, _writer_prompt

        prompt = _writer_prompt(DraftContext(kind="cover_letter", role="PM", company="Finlo"))
        assert "HARD WRITING RULES" not in prompt

    def test_profile_roundtrip_persists_rules(self, client):
        client.put("/api/profile", json={"style_rules": "Never use em dashes."})
        assert client.get("/api/profile").json()["style_rules"] == "Never use em dashes."
