import json
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.database.models import Job
from backend.importers.youtube import YoutubeError, check_limits, fetch_info, max_minutes

router = APIRouter(prefix="/api/youtube", tags=["youtube"])


class InfoBody(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class ImportBody(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    confirm_rights: bool = False


def _clean(url: str) -> str:
    u = url.strip()
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc:
        raise HTTPException(400, "Enter a full link starting with http:// or https://")
    return u


@router.post("/info")
def link_info(body: InfoBody):
    url = _clean(body.url)
    try:
        info = fetch_info(url)
        check_limits(info)
    except YoutubeError as e:
        raise HTTPException(400, str(e))
    return {**info, "max_minutes": max_minutes()}


@router.post("/import")
def start_import(body: ImportBody, db: Session = Depends(get_db)):
    if not body.confirm_rights:
        raise HTTPException(400, "Confirm that you own this video or have permission to use it.")
    url = _clean(body.url)
    job = Job(type="youtube_import", status="queued", payload=json.dumps({"url": url}))
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"job_id": job.id}