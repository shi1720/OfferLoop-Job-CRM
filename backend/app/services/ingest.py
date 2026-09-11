"""Bulk ingestion pipeline for the evaluation datasets.

Input schemas (exactly as specified by the problem statement):

    postings.csv : <id>, <from>, <to>, <type>, <description>
    drafts.csv   : <id>, <jobId>, <type>, <contents>, <status>

Design goals, in order:

1. **Never lose a good row.** Header aliasing (``<id>`` / ``id`` / ``ID``),
   UTF-8 BOM, CRLF, quoted multiline contents, several date formats, and
   messy type labels are all normalized. Bad rows are rejected
   individually with a row number and reason — one broken line never
   fails the file.
2. **Idempotent.** Rows carry their CSV id as ``external_id``; re-importing
   the same file — or a duplicated id *within* one file — resolves to an
   update, never a duplicate.
3. **Efficient.** Existing rows are indexed once per run (one repo read),
   so lookups are O(1) instead of a query per row; posting descriptions
   are structured by Gemini Flash in batched calls (with a regex
   fallback); embeddings are computed in batches; writes go to Firestore
   in batched commits.
4. **Integrated.** Drafts link to their posting via ``jobId``; orphans are
   kept with their ``jobId`` preserved and are adopted automatically when
   the missing posting arrives later; every run produces an auditable
   report.
"""

from __future__ import annotations

import csv
import io
import re
import time
from datetime import UTC, datetime

from ..models import (
    Application,
    Draft,
    DraftStatus,
    DraftType,
    FileReport,
    ImportReport,
    RowError,
    Status,
    StatusChange,
    utcnow,
)
from ..repos.base import Repo
from .llm import Intelligence

MAX_ROWS = 5000

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%Y/%m/%d",
    "%d %b %Y",
    "%b %d %Y",
    "%d %B %Y",
    "%B %d %Y",
    "%d.%m.%Y",
]


def _squash(label: str) -> str:
    """Normalize a type label: case, spaces, hyphens, underscores."""
    return re.sub(r"[\s_\-]+", "", (label or "").strip().lower())


# Keys are squashed, so "follow-up", "Follow Up", and "follow_up" all match.
_DRAFT_TYPE_ALIASES = {
    "coverletter": DraftType.COVER_LETTER,
    "letter": DraftType.COVER_LETTER,
    "followupemail": DraftType.FOLLOW_UP_EMAIL,
    "followup": DraftType.FOLLOW_UP_EMAIL,
    "email": DraftType.FOLLOW_UP_EMAIL,
    "thankyou": DraftType.FOLLOW_UP_EMAIL,
    "thankyouemail": DraftType.FOLLOW_UP_EMAIL,
}

_STATUS_ALIASES = {
    "draft": DraftStatus.DRAFT,
    "drafted": DraftStatus.DRAFT,
    "pending": DraftStatus.DRAFT,
    "sent": DraftStatus.SENT,
    "delivered": DraftStatus.SENT,
}

# Posting employment types collapse to a canonical vocabulary so analytics
# and filters never fragment across "full-time"/"full time"/"fulltime".
_JOB_TYPE_ALIASES = {
    "fulltime": "full-time",
    "parttime": "part-time",
    "contract": "contract",
    "contractor": "contract",
    "freelance": "contract",
    "internship": "internship",
    "intern": "internship",
}


def _normalize_job_type(raw: str) -> str:
    squashed = _squash(raw)
    return _JOB_TYPE_ALIASES.get(squashed, raw.strip().lower())


def _normalize_header(name: str) -> str:
    return (name or "").strip().strip("<>").strip().lower().replace(" ", "").replace("_", "")


def _detect_delimiter(header_line: str) -> str:
    """Pick the delimiter that splits the header into the most columns.

    (csv.Sniffer mis-detects dialects on files with quoted multiline
    fields, so we decide from the header row alone.)
    """
    return max(",;\t|", key=lambda d: header_line.count(d))


def _read_rows(data: bytes, spill_column: str) -> tuple[list[dict[str, str]], str | None]:
    """Decode + parse a CSV into dicts keyed by normalized header names.

    ``spill_column`` names the free-text column (``description`` /
    ``contents``). The evaluation examples contain UNQUOTED commas inside
    that column ("Senior Backend Engineer - Python, Bengaluru"), which
    naive parsing splits into extra fields — so when a row carries more
    fields than the header, the surplus is folded back into the spill
    column and the trailing columns are realigned.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        return [], "file has no header row"
    delimiter = _detect_delimiter(lines[0])

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        headers = [_normalize_header(h) for h in next(reader)]
    except StopIteration:
        return [], "file has no header row"
    spill_index = headers.index(spill_column) if spill_column in headers else None

    rows: list[dict[str, str]] = []
    for parts in reader:
        if not parts or all(not p.strip() for p in parts):
            continue
        surplus = len(parts) - len(headers)
        if surplus > 0 and spill_index is not None:
            merged = delimiter.join(parts[spill_index : spill_index + surplus + 1])
            parts = parts[:spill_index] + [merged] + parts[spill_index + surplus + 1 :]
        elif len(parts) < len(headers):
            parts = parts + [""] * (len(headers) - len(parts))
        rows.append({h: (v or "").strip() for h, v in zip(headers, parts, strict=False)})
        if len(rows) > MAX_ROWS:
            return [], f"file exceeds the {MAX_ROWS} row limit"
    return rows, None


def _parse_date(value: str) -> datetime | None:
    value = re.sub(r"\s+", " ", value.replace(",", " ")).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:  # full ISO timestamps
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Postings
# ---------------------------------------------------------------------------


def ingest_postings(
    repo: Repo,
    intelligence: Intelligence,
    uid: str,
    data: bytes,
    filename: str = "",
) -> FileReport:
    report = FileReport(filename=filename)
    rows, fatal = _read_rows(data, "description")
    if fatal:
        report.rejected.append(RowError(row=0, reason=fatal))
        return report
    report.total_rows = len(rows)

    valid: list[dict] = []
    for line, row in enumerate(rows, start=2):  # header is line 1
        ext_id = row.get("id", "")
        description = row.get("description", "")
        if not ext_id:
            report.rejected.append(RowError(row=line, reason="missing id"))
            continue
        if not description:
            report.rejected.append(RowError(row=line, reason="missing description"))
            continue
        date_from = _parse_date(row.get("from", ""))
        date_to = _parse_date(row.get("to", ""))
        if row.get("from") and date_from is None:
            report.rejected.append(RowError(row=line, reason=f"unparseable 'from' date: {row['from']!r}"))
            continue
        if row.get("to") and date_to is None:
            report.rejected.append(RowError(row=line, reason=f"unparseable 'to' date: {row['to']!r}"))
            continue
        valid.append(
            {
                "external_id": ext_id,
                "from": date_from,
                "to": date_to,
                "job_type": _normalize_job_type(row.get("type", "")),
                "description": description,
            }
        )

    # One batched Gemini call per ~40 rows turns free-text descriptions into
    # structured fields; regex fallback guarantees the import never fails.
    extracted = intelligence.extract_postings([v["description"] for v in valid])

    # One repo read builds the index; every row after that is O(1) — a
    # duplicated id inside the same file resolves to an update, not a twin.
    by_external: dict[str, Application] = {
        a.external_id: a for a in repo.list_applications(uid) if a.external_id
    }
    staged: dict[str, Application] = {}
    for item, fields in zip(valid, extracted, strict=True):
        existing = by_external.get(item["external_id"])
        applied_at = item["from"] or utcnow()
        if existing:
            existing.role = fields["role"] or existing.role
            existing.company = fields["company"] or existing.company
            existing.location = fields["location"] or existing.location
            existing.skills = fields["skills"] or existing.skills
            existing.job_type = item["job_type"] or existing.job_type
            existing.description = item["description"]
            existing.posting_from = item["from"]
            existing.posting_to = item["to"]
            existing.updated_at = utcnow()
            staged[existing.id] = existing
            report.updated += 1
        else:
            app = Application(
                uid=uid,
                external_id=item["external_id"],
                role=fields["role"],
                company=fields["company"],
                location=fields["location"],
                skills=fields["skills"],
                job_type=item["job_type"],
                description=item["description"],
                posting_from=item["from"],
                posting_to=item["to"],
                applied_at=applied_at,
                last_activity_at=applied_at,
                status=Status.APPLIED,
                status_history=[StatusChange(to_status=Status.APPLIED, at=applied_at, note="imported")],
                source="import",
            )
            by_external[app.external_id] = app
            staged[app.id] = app
            report.accepted += 1

    repo.bulk_put_applications(staged.values())
    return report


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------


def ingest_drafts(
    repo: Repo, intelligence: Intelligence, uid: str, data: bytes, filename: str = ""
) -> tuple[FileReport, int, int, int]:
    """Returns (report, linked, orphaned, embedded)."""
    report = FileReport(filename=filename)
    rows, fatal = _read_rows(data, "contents")
    if fatal:
        report.rejected.append(RowError(row=0, reason=fatal))
        return report, 0, 0, 0
    report.total_rows = len(rows)

    apps_by_external: dict[str, Application] = {
        a.external_id: a for a in repo.list_applications(uid) if a.external_id
    }
    drafts_by_external: dict[str, Draft] = {
        d.external_id: d for d in repo.list_drafts(uid) if d.external_id
    }

    linked = orphaned = 0
    staged: dict[str, Draft] = {}
    for line, row in enumerate(rows, start=2):
        ext_id = row.get("id", "")
        contents = row.get("contents", "")
        if not ext_id:
            report.rejected.append(RowError(row=line, reason="missing id"))
            continue
        if not contents:
            report.rejected.append(RowError(row=line, reason="missing contents"))
            continue
        dtype = _DRAFT_TYPE_ALIASES.get(_squash(row.get("type", "")))
        if dtype is None:
            report.rejected.append(RowError(row=line, reason=f"unknown draft type: {row.get('type')!r}"))
            continue
        dstatus = _STATUS_ALIASES.get(_squash(row.get("status", "draft")))
        if dstatus is None:
            report.rejected.append(RowError(row=line, reason=f"unknown status: {row.get('status')!r}"))
            continue

        job_ref = row.get("jobid", "")
        parent = apps_by_external.get(job_ref) if job_ref else None
        if parent:
            linked += 1
        else:
            orphaned += 1

        existing = drafts_by_external.get(ext_id)
        if existing:
            if existing.contents != contents:
                existing.embedding = None  # stale once the text changes
            existing.contents = contents
            existing.type = dtype
            existing.status = dstatus
            existing.external_job_id = job_ref or existing.external_job_id
            existing.application_id = parent.id if parent else existing.application_id
            existing.updated_at = utcnow()
            staged[existing.id] = existing
            report.updated += 1
        else:
            # The drafts schema carries no dates, so place historical drafts
            # near their application's date rather than "now" — this keeps
            # activity analytics honest and, crucially, never resets the
            # staleness clock that drives the follow-up cadence.
            written_at = parent.applied_at if parent else utcnow()
            draft = Draft(
                uid=uid,
                application_id=parent.id if parent else "",
                external_id=ext_id,
                external_job_id=job_ref or None,
                type=dtype,
                contents=contents,
                status=dstatus,
                source="imported",
                created_at=written_at,
                updated_at=written_at,
            )
            drafts_by_external[ext_id] = draft
            staged[draft.id] = draft
            report.accepted += 1

    # Batch-embed everything that has no vector yet so retrieval can use
    # semantic similarity in live mode. Lexical scoring covers the rest.
    embedded = 0
    pending = [d for d in staged.values() if d.embedding is None]
    vectors = intelligence.embed([d.contents for d in pending]) if pending else None
    if vectors:
        for draft, vector in zip(pending, vectors, strict=True):
            draft.embedding = vector
        embedded = len(pending)

    repo.bulk_put_drafts(staged.values())
    return report, linked, orphaned, embedded


# ---------------------------------------------------------------------------
# Orphan adoption — drafts whose posting arrived in a later import
# ---------------------------------------------------------------------------


def relink_orphans(repo: Repo, uid: str) -> int:
    """Attach previously orphaned drafts to postings that now exist."""
    apps_by_external = {a.external_id: a for a in repo.list_applications(uid) if a.external_id}
    adopted: list[Draft] = []
    for draft in repo.list_drafts(uid):
        if draft.application_id or not draft.external_job_id:
            continue
        parent = apps_by_external.get(draft.external_job_id)
        if parent:
            draft.application_id = parent.id
            draft.updated_at = utcnow()
            adopted.append(draft)
    if adopted:
        repo.bulk_put_drafts(adopted)
    return len(adopted)


# ---------------------------------------------------------------------------
# Combined run
# ---------------------------------------------------------------------------


def run_import(
    repo: Repo,
    intelligence: Intelligence,
    uid: str,
    postings: tuple[bytes, str] | None = None,
    drafts: tuple[bytes, str] | None = None,
) -> ImportReport:
    started = time.monotonic()
    report = ImportReport(uid=uid)
    if postings:
        report.postings = ingest_postings(repo, intelligence, uid, postings[0], postings[1])
    if drafts:
        draft_report, linked, orphaned, embedded = ingest_drafts(repo, intelligence, uid, drafts[0], drafts[1])
        report.drafts = draft_report
        report.linked_drafts = linked
        report.orphaned_drafts = orphaned
        report.embedded = embedded
    if postings:
        # Any drafts that were waiting for these postings — from this run or
        # any earlier one — get adopted now.
        report.relinked_drafts = relink_orphans(repo, uid)
    report.duration_ms = int((time.monotonic() - started) * 1000)
    repo.put_import_report(report)
    return report
