"""In-memory implementation of the Repo protocol.

Thread-safe enough for a demo server (FastAPI runs sync endpoints in a
threadpool), deterministic for tests, and free of any GCP dependency.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

from ..models import Application, Draft, ImportReport, Nudge, Profile


class MemoryRepo:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._applications: dict[str, dict[str, Application]] = {}
        self._drafts: dict[str, dict[str, Draft]] = {}
        self._nudges: dict[str, dict[str, Nudge]] = {}
        self._nudge_keys: dict[str, set[str]] = {}
        self._profiles: dict[str, Profile] = {}
        self._reports: dict[str, list[ImportReport]] = {}

    # -- applications ------------------------------------------------------
    def put_application(self, app: Application) -> None:
        with self._lock:
            self._applications.setdefault(app.uid, {})[app.id] = app.model_copy(deep=True)

    def bulk_put_applications(self, apps: Iterable[Application]) -> None:
        for app in apps:
            self.put_application(app)

    def get_application(self, uid: str, app_id: str) -> Application | None:
        with self._lock:
            app = self._applications.get(uid, {}).get(app_id)
            return app.model_copy(deep=True) if app else None

    def get_application_by_external_id(self, uid: str, external_id: str) -> Application | None:
        with self._lock:
            for app in self._applications.get(uid, {}).values():
                if app.external_id == external_id:
                    return app.model_copy(deep=True)
        return None

    def list_applications(self, uid: str) -> list[Application]:
        with self._lock:
            apps = [a.model_copy(deep=True) for a in self._applications.get(uid, {}).values()]
        return sorted(apps, key=lambda a: a.applied_at, reverse=True)

    def delete_application(self, uid: str, app_id: str) -> bool:
        with self._lock:
            removed = self._applications.get(uid, {}).pop(app_id, None)
            if removed:
                user_drafts = self._drafts.get(uid, {})
                for did in [d.id for d in user_drafts.values() if d.application_id == app_id]:
                    user_drafts.pop(did, None)
            return removed is not None

    # -- drafts ------------------------------------------------------------
    def put_draft(self, draft: Draft) -> None:
        with self._lock:
            self._drafts.setdefault(draft.uid, {})[draft.id] = draft.model_copy(deep=True)

    def bulk_put_drafts(self, drafts: Iterable[Draft]) -> None:
        for draft in drafts:
            self.put_draft(draft)

    def get_draft(self, uid: str, draft_id: str) -> Draft | None:
        with self._lock:
            draft = self._drafts.get(uid, {}).get(draft_id)
            return draft.model_copy(deep=True) if draft else None

    def get_draft_by_external_id(self, uid: str, external_id: str) -> Draft | None:
        with self._lock:
            for draft in self._drafts.get(uid, {}).values():
                if draft.external_id == external_id:
                    return draft.model_copy(deep=True)
        return None

    def list_drafts(self, uid: str, application_id: str | None = None) -> list[Draft]:
        with self._lock:
            drafts = [d.model_copy(deep=True) for d in self._drafts.get(uid, {}).values()]
        if application_id is not None:
            drafts = [d for d in drafts if d.application_id == application_id]
        return sorted(drafts, key=lambda d: d.created_at, reverse=True)

    # -- nudges ------------------------------------------------------------
    def create_nudge_if_absent(self, nudge: Nudge) -> bool:
        with self._lock:
            keys = self._nudge_keys.setdefault(nudge.uid, set())
            if nudge.dedupe_key in keys:
                return False
            keys.add(nudge.dedupe_key)
            self._nudges.setdefault(nudge.uid, {})[nudge.id] = nudge.model_copy(deep=True)
            return True

    def list_nudges(self, uid: str, status: str | None = None) -> list[Nudge]:
        with self._lock:
            nudges = [n.model_copy(deep=True) for n in self._nudges.get(uid, {}).values()]
        if status is not None:
            nudges = [n for n in nudges if n.status.value == status]
        return sorted(nudges, key=lambda n: n.due_at, reverse=True)

    def get_nudge(self, uid: str, nudge_id: str) -> Nudge | None:
        with self._lock:
            nudge = self._nudges.get(uid, {}).get(nudge_id)
            return nudge.model_copy(deep=True) if nudge else None

    def update_nudge(self, nudge: Nudge) -> None:
        with self._lock:
            self._nudges.setdefault(nudge.uid, {})[nudge.id] = nudge.model_copy(deep=True)

    # -- scan --------------------------------------------------------------
    def scan_users(self) -> list[str]:
        with self._lock:
            return [uid for uid, apps in self._applications.items() if apps]

    # -- profile / reports -------------------------------------------------
    def get_profile(self, uid: str) -> Profile | None:
        with self._lock:
            profile = self._profiles.get(uid)
            return profile.model_copy(deep=True) if profile else None

    def put_profile(self, profile: Profile) -> None:
        with self._lock:
            self._profiles[profile.uid] = profile.model_copy(deep=True)

    def put_import_report(self, report: ImportReport) -> None:
        with self._lock:
            self._reports.setdefault(report.uid, []).insert(0, report.model_copy(deep=True))

    def list_import_reports(self, uid: str, limit: int = 10) -> list[ImportReport]:
        with self._lock:
            return [r.model_copy(deep=True) for r in self._reports.get(uid, [])[:limit]]

    # -- misc ---------------------------------------------------------------
    def is_empty(self, uid: str) -> bool:
        with self._lock:
            return not self._applications.get(uid)
