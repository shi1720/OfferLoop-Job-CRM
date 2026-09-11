"""Firestore implementation of the Repo protocol.

Layout (all user data lives under the user's namespace, which is also what
the security rules in ``infra/firestore.rules`` enforce for any direct
client access):

    users/{uid}                          — registry doc (uid, updated_at)
    users/{uid}/applications/{appId}
    users/{uid}/drafts/{draftId}
    users/{uid}/nudges/{dedupeKey}       — doc id IS the dedupe key
    users/{uid}/meta/profile
    users/{uid}/imports/{reportId}

Writes use batched commits (Firestore caps a batch at 500 ops) so a bulk
CSV import of hundreds of rows lands in a handful of round trips.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from ..models import Application, Draft, ImportReport, Nudge, Profile

_BATCH_LIMIT = 450  # headroom under Firestore's 500-op cap


def _key(raw: str) -> str:
    """Make an arbitrary string safe to use as a Firestore document id."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", raw)[:1400] or "_"


class FirestoreRepo:
    def __init__(self, project: str, database: str = "(default)") -> None:
        from google.cloud import firestore  # deferred: only needed in live mode

        self._db = firestore.Client(project=project or None, database=database)
        self._firestore = firestore

    # -- helpers -----------------------------------------------------------
    def _user(self, uid: str):
        return self._db.collection("users").document(uid)

    def _register_user(self, uid: str) -> None:
        from ..models import utcnow

        self._user(uid).set({"uid": uid, "updated_at": utcnow()}, merge=True)

    @staticmethod
    def _dump(model: Any) -> dict:
        return model.model_dump(mode="json")

    def _bulk(self, uid: str, collection: str, items: list[Any]) -> None:
        self._register_user(uid)
        docs = self._user(uid).collection(collection)
        for start in range(0, len(items), _BATCH_LIMIT):
            batch = self._db.batch()
            for item in items[start : start + _BATCH_LIMIT]:
                batch.set(docs.document(item.id), self._dump(item))
            batch.commit()

    # -- applications ------------------------------------------------------
    def put_application(self, app: Application) -> None:
        self._register_user(app.uid)
        self._user(app.uid).collection("applications").document(app.id).set(self._dump(app))

    def bulk_put_applications(self, apps: Iterable[Application]) -> None:
        grouped: dict[str, list[Application]] = {}
        for app in apps:
            grouped.setdefault(app.uid, []).append(app)
        for uid, items in grouped.items():
            self._bulk(uid, "applications", items)

    def get_application(self, uid: str, app_id: str) -> Application | None:
        snap = self._user(uid).collection("applications").document(app_id).get()
        return Application.model_validate(snap.to_dict()) if snap.exists else None

    def get_application_by_external_id(self, uid: str, external_id: str) -> Application | None:
        query = (
            self._user(uid)
            .collection("applications")
            .where(filter=self._filter("external_id", "==", external_id))
            .limit(1)
        )
        for snap in query.stream():
            return Application.model_validate(snap.to_dict())
        return None

    def list_applications(self, uid: str) -> list[Application]:
        snaps = self._user(uid).collection("applications").stream()
        apps = [Application.model_validate(s.to_dict()) for s in snaps]
        return sorted(apps, key=lambda a: a.applied_at, reverse=True)

    def delete_application(self, uid: str, app_id: str) -> bool:
        doc = self._user(uid).collection("applications").document(app_id)
        existed = doc.get().exists
        if existed:
            doc.delete()
            drafts = (
                self._user(uid)
                .collection("drafts")
                .where(filter=self._filter("application_id", "==", app_id))
                .stream()
            )
            refs = [snap.reference for snap in drafts]
            for start in range(0, len(refs), _BATCH_LIMIT):
                batch = self._db.batch()
                for ref in refs[start : start + _BATCH_LIMIT]:
                    batch.delete(ref)
                batch.commit()
        return existed

    # -- drafts ------------------------------------------------------------
    def put_draft(self, draft: Draft) -> None:
        self._user(draft.uid).collection("drafts").document(draft.id).set(self._dump(draft))

    def bulk_put_drafts(self, drafts: Iterable[Draft]) -> None:
        grouped: dict[str, list[Draft]] = {}
        for draft in drafts:
            grouped.setdefault(draft.uid, []).append(draft)
        for uid, items in grouped.items():
            self._bulk(uid, "drafts", items)

    def get_draft(self, uid: str, draft_id: str) -> Draft | None:
        snap = self._user(uid).collection("drafts").document(draft_id).get()
        return Draft.model_validate(snap.to_dict()) if snap.exists else None

    def get_draft_by_external_id(self, uid: str, external_id: str) -> Draft | None:
        query = (
            self._user(uid)
            .collection("drafts")
            .where(filter=self._filter("external_id", "==", external_id))
            .limit(1)
        )
        for snap in query.stream():
            return Draft.model_validate(snap.to_dict())
        return None

    def list_drafts(self, uid: str, application_id: str | None = None) -> list[Draft]:
        coll = self._user(uid).collection("drafts")
        if application_id is not None:
            coll = coll.where(filter=self._filter("application_id", "==", application_id))
        drafts = [Draft.model_validate(s.to_dict()) for s in coll.stream()]
        return sorted(drafts, key=lambda d: d.created_at, reverse=True)

    # -- nudges ------------------------------------------------------------
    def create_nudge_if_absent(self, nudge: Nudge) -> bool:
        from google.api_core.exceptions import AlreadyExists

        doc = self._user(nudge.uid).collection("nudges").document(_key(nudge.dedupe_key))
        try:
            doc.create(self._dump(nudge))
            return True
        except AlreadyExists:
            return False

    def list_nudges(self, uid: str, status: str | None = None) -> list[Nudge]:
        coll = self._user(uid).collection("nudges")
        if status is not None:
            coll = coll.where(filter=self._filter("status", "==", status))
        nudges = [Nudge.model_validate(s.to_dict()) for s in coll.stream()]
        return sorted(nudges, key=lambda n: n.due_at, reverse=True)

    def get_nudge(self, uid: str, nudge_id: str) -> Nudge | None:
        query = (
            self._user(uid)
            .collection("nudges")
            .where(filter=self._filter("id", "==", nudge_id))
            .limit(1)
        )
        for snap in query.stream():
            return Nudge.model_validate(snap.to_dict())
        return None

    def update_nudge(self, nudge: Nudge) -> None:
        self._user(nudge.uid).collection("nudges").document(_key(nudge.dedupe_key)).set(
            self._dump(nudge)
        )

    # -- scan --------------------------------------------------------------
    def scan_users(self) -> list[str]:
        return [snap.id for snap in self._db.collection("users").stream()]

    # -- profile / reports -------------------------------------------------
    def get_profile(self, uid: str) -> Profile | None:
        snap = self._user(uid).collection("meta").document("profile").get()
        return Profile.model_validate(snap.to_dict()) if snap.exists else None

    def put_profile(self, profile: Profile) -> None:
        self._register_user(profile.uid)
        self._user(profile.uid).collection("meta").document("profile").set(self._dump(profile))

    def put_import_report(self, report: ImportReport) -> None:
        self._user(report.uid).collection("imports").document(report.id).set(self._dump(report))

    def list_import_reports(self, uid: str, limit: int = 10) -> list[ImportReport]:
        snaps = self._user(uid).collection("imports").stream()
        reports = [ImportReport.model_validate(s.to_dict()) for s in snaps]
        return sorted(reports, key=lambda r: r.created_at, reverse=True)[:limit]

    # -- misc ---------------------------------------------------------------
    def is_empty(self, uid: str) -> bool:
        snaps = self._user(uid).collection("applications").limit(1).stream()
        return next(iter(snaps), None) is None

    @staticmethod
    def _filter(field: str, op: str, value: Any):
        from google.cloud.firestore_v1.base_query import FieldFilter

        return FieldFilter(field, op, value)
