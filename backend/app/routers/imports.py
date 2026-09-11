"""Bulk CSV import endpoint + import history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..auth import User, get_current_user
from ..config import Settings, get_settings
from ..deps import get_intelligence, get_repo
from ..repos.base import Repo
from ..services.ingest import run_import
from ..services.llm import Intelligence

router = APIRouter(prefix="/api/import", tags=["import"])

_MAX_UPLOAD_BYTES = 5 * 1024 * 1024


async def _read_limited(upload: UploadFile | None) -> tuple[bytes, str] | None:
    if upload is None:
        return None
    data = await upload.read()
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"{upload.filename}: file exceeds 5 MB")
    if not data:
        raise HTTPException(status_code=422, detail=f"{upload.filename}: file is empty")
    return data, upload.filename or ""


@router.post("")
async def import_csvs(
    postings: UploadFile | None = File(default=None),
    drafts: UploadFile | None = File(default=None),
    user: User = Depends(get_current_user),
    repo: Repo = Depends(get_repo),
    intelligence: Intelligence = Depends(get_intelligence),
):
    """Ingest the evaluation datasets.

    Accepts either or both files in one request. Postings are processed
    first so drafts in the same request can link to them by ``jobId``.
    """
    postings_payload = await _read_limited(postings)
    drafts_payload = await _read_limited(drafts)
    if postings_payload is None and drafts_payload is None:
        raise HTTPException(status_code=422, detail="Provide a postings and/or drafts CSV")

    return run_import(repo, intelligence, user.uid, postings=postings_payload, drafts=drafts_payload)


@router.get("/history")
def import_history(user: User = Depends(get_current_user), repo: Repo = Depends(get_repo)):
    return repo.list_import_reports(user.uid)


@router.get("/samples/{name}")
def sample_dataset(
    name: str,
    _: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
):
    """Serve the bundled sample CSVs so the UI's "try with sample data"
    button runs the real import pipeline against known-good files."""
    from pathlib import Path

    from fastapi.responses import PlainTextResponse

    from ..seed import _data_dir

    if name not in {"postings", "drafts"}:
        raise HTTPException(status_code=404, detail="Unknown sample")
    path = Path(_data_dir(settings)) / f"sample_{name}.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Sample dataset not bundled")
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/csv")
