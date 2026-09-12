"""Domain models.

The vocabulary here deliberately mirrors the evaluation dataset schemas:

- postings CSV : ``id, from, to, type, description``
- drafts CSV   : ``id, jobId, type, contents, status``

so an imported row maps 1:1 onto a domain object with no lossy renaming.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def utcnow() -> datetime:
    return datetime.now(UTC)


def _ensure_utc(value: datetime) -> datetime:
    """Coerce naive datetimes (e.g. a bare "2026-08-15" in an API payload)
    to UTC so aware/naive comparisons can never 500 a request."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


UTCDateTime = Annotated[datetime, AfterValidator(_ensure_utc)]


# ---------------------------------------------------------------------------
# Enums — the four pipeline phases named by the problem statement.
# ---------------------------------------------------------------------------


class Status(StrEnum):
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECT = "reject"


class DraftType(StrEnum):
    COVER_LETTER = "cover_letter"
    FOLLOW_UP_EMAIL = "follow_up_email"
    REFERRAL_REQUEST = "referral_request"
    LINKEDIN_MESSAGE = "linkedin_message"


class DraftStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"


class NudgeStatus(StrEnum):
    PENDING = "pending"
    DONE = "done"
    DISMISSED = "dismissed"


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------


class StatusChange(BaseModel):
    from_status: Status | None = None
    to_status: Status
    at: UTCDateTime
    note: str = ""


class PrepQuestion(BaseModel):
    question: str
    why_they_ask: str = ""
    how_to_answer: str = ""


class PrepStory(BaseModel):
    title: str
    outline: str = ""  # STAR-shaped prompt built from the user's proof points
    metric: str = ""  # the number to land


class PrepPack(BaseModel):
    """Interview prep generated per application, grounded on the posting
    and the candidate's own profile — regenerated on demand, never stale."""

    questions: list[PrepQuestion] = Field(default_factory=list)
    stories: list[PrepStory] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)
    model: str = ""
    generated_at: UTCDateTime = Field(default_factory=utcnow)


class Application(BaseModel):
    id: str = Field(default_factory=new_id)
    uid: str
    external_id: str | None = None  # id column of an imported posting
    company: str = ""
    role: str
    location: str = ""
    job_type: str = ""  # full-time | contract | internship | ...
    description: str = ""  # raw posting text — the grounding source
    skills: list[str] = Field(default_factory=list)
    posting_url: str = ""  # original posting link (paste-a-link capture, tracker imports)
    posting_from: UTCDateTime | None = None
    posting_to: UTCDateTime | None = None
    applied_at: UTCDateTime = Field(default_factory=utcnow)
    status: Status = Status.APPLIED
    status_history: list[StatusChange] = Field(default_factory=list)
    last_activity_at: UTCDateTime = Field(default_factory=utcnow)
    source: str = "manual"  # manual | import | capture
    notes: str = ""
    contact_name: str = ""  # recruiter / referrer — a CRM needs a who
    contact_email: str = ""
    interview_at: UTCDateTime | None = None  # next interview, drives calendar links
    prep_pack: PrepPack | None = None
    deleted_at: UTCDateTime | None = None  # soft delete → undo is possible
    created_at: UTCDateTime = Field(default_factory=utcnow)
    updated_at: UTCDateTime = Field(default_factory=utcnow)

    def touch(self, at: datetime | None = None) -> None:
        now = at or utcnow()
        self.last_activity_at = now
        self.updated_at = now


class Draft(BaseModel):
    id: str = Field(default_factory=new_id)
    uid: str
    application_id: str
    external_id: str | None = None  # id column of an imported draft
    external_job_id: str | None = None  # jobId column — kept so orphans can relink later
    type: DraftType
    subject: str = ""
    contents: str
    status: DraftStatus = DraftStatus.DRAFT
    source: str = "generated"  # generated | imported | edited
    model: str = ""  # which Gemini model produced it, if generated
    grounded_on: list[str] = Field(default_factory=list)  # draft ids used as voice references
    embedding: list[float] | None = None
    created_at: UTCDateTime = Field(default_factory=utcnow)
    updated_at: UTCDateTime = Field(default_factory=utcnow)


class Nudge(BaseModel):
    id: str = Field(default_factory=new_id)
    uid: str
    application_id: str
    rule: str
    touch: int = 1  # 1st, 2nd, 3rd follow-up in the cadence
    headline: str
    detail: str = ""
    due_at: UTCDateTime
    status: NudgeStatus = NudgeStatus.PENDING
    draft_id: str | None = None  # auto-drafted follow-up attached to the nudge
    dedupe_key: str = ""
    created_at: UTCDateTime = Field(default_factory=utcnow)


class Profile(BaseModel):
    uid: str
    name: str = ""
    headline: str = ""
    years_experience: float = 0
    skills: list[str] = Field(default_factory=list)
    tone: str = "warm, direct, confident"
    achievements: str = ""
    style_rules: str = ""  # hard writing constraints applied to every draft
    gemini_api_key_enc: str = ""  # user's own key (encrypted at rest; never returned)
    free_used: int = 0  # server-key generations consumed from the free allowance
    onboarded: bool = False  # first-login tour completed/skipped
    points: int = 0  # momentum score, awarded server-side
    weekly_goal: int = 5  # target applications per week (Today view ring)
    push_tokens: list[str] = Field(default_factory=list)  # FCM web push tokens (≤5 devices)


# ---------------------------------------------------------------------------
# Import pipeline reporting
# ---------------------------------------------------------------------------


class RowError(BaseModel):
    row: int
    reason: str


class FileReport(BaseModel):
    filename: str = ""
    total_rows: int = 0
    accepted: int = 0
    updated: int = 0  # idempotent re-imports resolve to updates, not dupes
    rejected: list[RowError] = Field(default_factory=list)


class ImportReport(BaseModel):
    id: str = Field(default_factory=new_id)
    uid: str = ""
    postings: FileReport = Field(default_factory=FileReport)
    drafts: FileReport = Field(default_factory=FileReport)
    linked_drafts: int = 0
    orphaned_drafts: int = 0  # drafts whose jobId matched no posting (yet)
    relinked_drafts: int = 0  # previously orphaned drafts adopted by newly imported postings
    embedded: int = 0
    duration_ms: int = 0
    created_at: UTCDateTime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# API request/response shapes
# ---------------------------------------------------------------------------


class ApplicationCreate(BaseModel):
    company: str = ""
    role: str
    location: str = ""
    job_type: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)  # prefilled by capture
    posting_url: str = ""
    contact_name: str = ""
    contact_email: str = ""
    applied_at: UTCDateTime | None = None
    status: Status = Status.APPLIED
    notes: str = ""


class ApplicationUpdate(BaseModel):
    company: str | None = None
    role: str | None = None
    location: str | None = None
    job_type: str | None = None
    description: str | None = None
    posting_url: str | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    status: Status | None = None
    status_note: str = ""
    notes: str | None = None
    interview_at: UTCDateTime | None = None
    clear_interview: bool = False  # None means "not provided", so clearing needs a flag


class CaptureRequest(BaseModel):
    """Paste-a-link (or paste-the-JD) quick capture."""

    url: str = ""
    text: str = ""


class CapturedPosting(BaseModel):
    """Extracted posting fields, returned for the user to confirm — capture
    never creates the application behind their back."""

    role: str = ""
    company: str = ""
    location: str = ""
    job_type: str = ""
    skills: list[str] = Field(default_factory=list)
    description: str = ""
    posting_url: str = ""


class PushTokenUpdate(BaseModel):
    token: str


class GenerateRequest(BaseModel):
    type: DraftType
    instructions: str = ""  # optional user steering, e.g. "mention the referral"


class DraftUpdate(BaseModel):
    subject: str | None = None
    contents: str | None = None
    status: DraftStatus | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    headline: str | None = None
    years_experience: float | None = None
    skills: list[str] | None = None
    tone: str | None = None
    achievements: str | None = None
    style_rules: str | None = None
    onboarded: bool | None = None
    weekly_goal: int | None = Field(default=None, ge=0, le=100)


class GeminiKeyUpdate(BaseModel):
    key: str


class PublicProfile(BaseModel):
    """Profile as the API returns it — the raw key never leaves the server."""

    uid: str
    name: str = ""
    headline: str = ""
    years_experience: float = 0
    skills: list[str] = Field(default_factory=list)
    tone: str = ""
    achievements: str = ""
    style_rules: str = ""
    onboarded: bool = False
    points: int = 0
    level: str = "Starter"
    gemini_key_masked: str | None = None  # "\u2022\u2022\u2022\u2022 1a2b" or None
    free_remaining: int = 0
    engine: str = "demo"  # your_key | free_credits | key_required | demo
    weekly_goal: int = 5
    push_enabled: bool = False  # at least one registered web-push device


class ScanReport(BaseModel):
    scanned: int = 0
    nudges_created: int = 0
    drafts_generated: int = 0
    duration_ms: int = 0
