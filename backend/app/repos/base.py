"""Storage interface.

Two implementations exist:

- ``MemoryRepo``    — dict-backed, used in demo mode, CI, and tests.
- ``FirestoreRepo`` — the production store on Google Cloud Firestore.

Routers and services only ever see this protocol, which is what lets the
entire product run and be tested end-to-end before a GCP project exists,
then switch with one environment variable.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from ..models import Application, Draft, ImportReport, Nudge, Profile


class Repo(Protocol):
    # -- applications ------------------------------------------------------
    def put_application(self, app: Application) -> None: ...

    def bulk_put_applications(self, apps: Iterable[Application]) -> None: ...

    def get_application(self, uid: str, app_id: str) -> Application | None: ...

    def get_application_by_external_id(self, uid: str, external_id: str) -> Application | None: ...

    def list_applications(self, uid: str) -> list[Application]: ...

    def delete_application(self, uid: str, app_id: str) -> bool: ...

    # -- drafts ------------------------------------------------------------
    def put_draft(self, draft: Draft) -> None: ...

    def bulk_put_drafts(self, drafts: Iterable[Draft]) -> None: ...

    def get_draft(self, uid: str, draft_id: str) -> Draft | None: ...

    def get_draft_by_external_id(self, uid: str, external_id: str) -> Draft | None: ...

    def list_drafts(self, uid: str, application_id: str | None = None) -> list[Draft]: ...

    # -- nudges ------------------------------------------------------------
    def create_nudge_if_absent(self, nudge: Nudge) -> bool:
        """Insert keyed on ``dedupe_key``; return False if it already exists.

        This single method is what makes the scheduled scan idempotent: the
        scan can run every hour (or be retried by Cloud Scheduler) without
        ever double-nudging a user.
        """
        ...

    def list_nudges(self, uid: str, status: str | None = None) -> list[Nudge]: ...

    def get_nudge(self, uid: str, nudge_id: str) -> Nudge | None: ...

    def update_nudge(self, nudge: Nudge) -> None: ...

    # -- scan --------------------------------------------------------------
    def scan_users(self) -> list[str]:
        """User ids that have at least one application (nudge-scan universe)."""
        ...

    # -- profile / reports -------------------------------------------------
    def get_profile(self, uid: str) -> Profile | None: ...

    def put_profile(self, profile: Profile) -> None: ...

    def put_import_report(self, report: ImportReport) -> None: ...

    def list_import_reports(self, uid: str, limit: int = 10) -> list[ImportReport]: ...

    # -- misc ---------------------------------------------------------------
    def is_empty(self, uid: str) -> bool: ...


def stale_cutoff(now: datetime, days: int) -> datetime:
    from datetime import timedelta

    return now - timedelta(days=days)
