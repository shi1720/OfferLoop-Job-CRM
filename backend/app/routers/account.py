"""Your data, your call: CSV export and full account deletion.

No lock-in is a feature — everything the user ever entered leaves in the
same shape it arrived (flat CSVs), and delete means delete.
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from ..auth import User, get_current_user
from ..deps import get_repo
from ..repos.base import Repo

router = APIRouter(prefix="/api", tags=["account"])

_APP_COLUMNS = [
    "id",
    "external_id",
    "company",
    "role",
    "location",
    "job_type",
    "status",
    "applied_at",
    "last_activity_at",
    "posting_url",
    "contact_name",
    "contact_email",
    "interview_at",
    "skills",
    "notes",
    "status_history",
    "description",
]

_DRAFT_COLUMNS = ["id", "application_id", "type", "status", "subject", "created_at", "contents"]


def _csv_response(filename: str, columns: list[str], rows: list[list[str]]) -> PlainTextResponse:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    return PlainTextResponse(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/applications.csv")
def export_applications(user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    rows = []
    for app in repo.list_applications(user.uid):
        history = " > ".join(f"{c.to_status.value}@{c.at.date().isoformat()}" for c in app.status_history)
        rows.append(
            [
                app.id,
                app.external_id or "",
                app.company,
                app.role,
                app.location,
                app.job_type,
                app.status.value,
                app.applied_at.isoformat(),
                app.last_activity_at.isoformat(),
                app.posting_url,
                app.contact_name,
                app.contact_email,
                app.interview_at.isoformat() if app.interview_at else "",
                ", ".join(app.skills),
                app.notes,
                history,
                app.description,
            ]
        )
    return _csv_response("offerloop_applications.csv", _APP_COLUMNS, rows)


@router.get("/export/drafts.csv")
def export_drafts(user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    live_ids = {a.id for a in repo.list_applications(user.uid)}
    rows = [
        [d.id, d.application_id, d.type.value, d.status.value, d.subject, d.created_at.isoformat(), d.contents]
        for d in repo.list_drafts(user.uid)
        if not d.application_id or d.application_id in live_ids
    ]
    return _csv_response("offerloop_drafts.csv", _DRAFT_COLUMNS, rows)


@router.delete("/account", status_code=204)
def delete_account(user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    """Erase every application, draft, nudge, report, and the profile.

    Irreversible by design; the UI double-confirms before calling this.
    """
    if not user.uid:
        raise HTTPException(status_code=401, detail="No user")
    repo.delete_user_data(user.uid)
