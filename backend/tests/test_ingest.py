"""The importer is the most heavily evaluated surface — test it hard."""

from __future__ import annotations

import io

from app.services.ingest import ingest_drafts, ingest_postings, run_import

POSTINGS = (
    b"id,from,to,type,description\n"
    b"1,2026-06-01,2026-06-30,full-time,Senior Backend Engineer - Python, Bengaluru\n"
    b'2,2026-06-10,2026-07-10,contract,"Data Platform Engineer - streaming pipelines"\n'
)

DRAFTS = (
    b"id,jobId,type,contents,status\n"
    b'1,1,cover_letter,"Dear Hiring Manager - I\'m applying for the backend role...",draft\n'
    b'2,1,follow_up_email,"Following up on my application from June 12...",sent\n'
    b'3,42,follow_up_email,"This jobId does not exist",draft\n'
)


def _csv(text: str) -> bytes:
    return text.encode()


class TestPostings:
    def test_happy_path_matches_eval_schema(self, repo, intelligence):
        report = ingest_postings(repo, intelligence, "u1", POSTINGS)
        assert report.accepted == 2
        assert report.rejected == []
        apps = repo.list_applications("u1")
        assert {a.external_id for a in apps} == {"1", "2"}
        senior = repo.get_application_by_external_id("u1", "1")
        assert senior.role == "Senior Backend Engineer"
        assert senior.location == "Bengaluru"
        assert senior.job_type == "full-time"
        assert senior.applied_at.date().isoformat() == "2026-06-01"

    def test_angle_bracket_headers_and_bom(self, repo, intelligence):
        data = "﻿<id>,<from>,<to>,<type>,<description>\r\n9,2026-05-01,2026-05-30,full-time,SRE at Skylane - GCP, Remote\r\n"
        report = ingest_postings(repo, intelligence, "u1", _csv(data))
        assert report.accepted == 1
        app = repo.get_application_by_external_id("u1", "9")
        assert app.company == "Skylane"
        assert app.location == "Remote"

    def test_alternate_date_formats(self, repo, intelligence):
        data = "id,from,to,type,description\n1,15/06/2026,30-06-2026,full-time,Backend Engineer - Python\n"
        report = ingest_postings(repo, intelligence, "u1", _csv(data))
        assert report.accepted == 1
        app = repo.get_application_by_external_id("u1", "1")
        assert app.applied_at.date().isoformat() == "2026-06-15"

    def test_bad_rows_rejected_individually(self, repo, intelligence):
        data = (
            "id,from,to,type,description\n"
            "1,2026-06-01,2026-06-30,full-time,Good row - Python\n"
            ",2026-06-01,2026-06-30,full-time,Missing id\n"
            "3,not-a-date,2026-06-30,full-time,Bad date - Python\n"
            "4,2026-06-01,2026-06-30,full-time,\n"
        )
        report = ingest_postings(repo, intelligence, "u1", _csv(data))
        assert report.accepted == 1
        reasons = [e.reason for e in report.rejected]
        assert len(reasons) == 3
        assert any("missing id" in r for r in reasons)
        assert any("unparseable" in r for r in reasons)
        assert any("missing description" in r for r in reasons)

    def test_reimport_is_idempotent(self, repo, intelligence):
        first = ingest_postings(repo, intelligence, "u1", POSTINGS)
        second = ingest_postings(repo, intelligence, "u1", POSTINGS)
        assert first.accepted == 2
        assert second.accepted == 0
        assert second.updated == 2
        assert len(repo.list_applications("u1")) == 2

    def test_semicolon_delimiter_sniffed(self, repo, intelligence):
        data = "id;from;to;type;description\n7;2026-06-01;2026-06-30;full-time;Platform Engineer - GCP\n"
        report = ingest_postings(repo, intelligence, "u1", _csv(data))
        assert report.accepted == 1

    def test_empty_file_is_a_clean_error(self, repo, intelligence):
        report = ingest_postings(repo, intelligence, "u1", b"")
        assert report.accepted == 0
        assert report.rejected and report.rejected[0].row == 0


class TestDrafts:
    def test_linking_and_orphans(self, repo, intelligence):
        ingest_postings(repo, intelligence, "u1", POSTINGS)
        report, linked, orphaned, _ = ingest_drafts(repo, intelligence, "u1", DRAFTS)
        assert report.accepted == 3
        assert linked == 2
        assert orphaned == 1
        parent = repo.get_application_by_external_id("u1", "1")
        drafts = repo.list_drafts("u1", parent.id)
        assert len(drafts) == 2
        assert {d.type.value for d in drafts} == {"cover_letter", "follow_up_email"}

    def test_multiline_quoted_contents(self, repo, intelligence):
        ingest_postings(repo, intelligence, "u1", POSTINGS)
        data = 'id,jobId,type,contents,status\n5,1,cover_letter,"Dear Team,\n\nTwo paragraphs, one comma, and a ""quote"".\n\nRegards",sent\n'
        report, linked, _, _ = ingest_drafts(repo, intelligence, "u1", _csv(data))
        assert report.accepted == 1 and linked == 1
        draft = repo.get_draft_by_external_id("u1", "5")
        assert "\n\n" in draft.contents
        assert '"quote"' in draft.contents

    def test_type_aliases_normalized(self, repo, intelligence):
        data = (
            "id,jobId,type,contents,status\n"
            "1,,cover letter,Some letter,draft\n"
            "2,,followup,Some follow up,sent\n"
            "3,,carrier_pigeon,Nope,draft\n"
        )
        report, _, _, _ = ingest_drafts(repo, intelligence, "u1", _csv(data))
        assert report.accepted == 2
        assert len(report.rejected) == 1
        assert "unknown draft type" in report.rejected[0].reason

    def test_import_never_resets_staleness_clock(self, repo, intelligence):
        # Historical drafts are history, not fresh outreach — importing them
        # must not silence the follow-up cadence.
        ingest_postings(repo, intelligence, "u1", POSTINGS)
        before = repo.get_application_by_external_id("u1", "1").last_activity_at
        ingest_drafts(repo, intelligence, "u1", DRAFTS)
        after = repo.get_application_by_external_id("u1", "1").last_activity_at
        assert after == before

    def test_imported_drafts_dated_near_their_application(self, repo, intelligence):
        ingest_postings(repo, intelligence, "u1", POSTINGS)
        ingest_drafts(repo, intelligence, "u1", DRAFTS)
        parent = repo.get_application_by_external_id("u1", "1")
        draft = repo.get_draft_by_external_id("u1", "1")
        assert draft.created_at == parent.applied_at


class TestRunImport:
    def test_combined_run_produces_report(self, repo, intelligence):
        report = run_import(repo, intelligence, "u1", postings=(POSTINGS, "p.csv"), drafts=(DRAFTS, "d.csv"))
        assert report.postings.accepted == 2
        assert report.drafts.accepted == 3
        assert report.linked_drafts == 2
        assert report.orphaned_drafts == 1
        assert repo.list_import_reports("u1")[0].id == report.id


class TestImportApi:
    def test_multipart_upload(self, client):
        response = client.post(
            "/api/import",
            files={
                "postings": ("postings.csv", io.BytesIO(POSTINGS), "text/csv"),
                "drafts": ("drafts.csv", io.BytesIO(DRAFTS), "text/csv"),
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["postings"]["accepted"] == 2
        assert body["linked_drafts"] == 2

    def test_upload_requires_at_least_one_file(self, client):
        assert client.post("/api/import").status_code == 422

    def test_empty_file_rejected(self, client):
        response = client.post("/api/import", files={"postings": ("p.csv", io.BytesIO(b""), "text/csv")})
        assert response.status_code == 422
