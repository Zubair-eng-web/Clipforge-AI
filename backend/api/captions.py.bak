import json
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.clips import clip_dict
from backend.captions.builder import to_srt
from backend.captions.burn import has_subtitles_filter
from backend.database.db import get_db
from backend.database.models import Clip, ClipCaption, Job

router = APIRouter(prefix="/api/clips", tags=["captions"])
MAX_LINES = 500


class GenerateBody(BaseModel):
    language: Optional[str] = None  # None / "auto" = detect


class LineIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(max_length=300)


class SaveBody(BaseModel):
    lines: list[LineIn]


class BurnBody(BaseModel):
    style: Literal["classic", "bold", "highlight"] = "classic"
    position: Literal["bottom", "center", "top"] = "bottom"
    font_size: Optional[int] = Field(default=None, ge=12, le=200)


def _clip_or_404(db: Session, clip_id: int) -> Clip:
    c = db.get(Clip, clip_id)
    if not c:
        raise HTTPException(404, "Clip not found")
    return c


def _ready_clip(db: Session, clip_id: int) -> Clip:
    c = _clip_or_404(db, clip_id)
    if c.status != "ready" or not c.file_path:
        raise HTTPException(409, "The clip is not ready yet")
    return c


def _caption_row(db: Session, clip_id: int):
    return db.scalar(select(ClipCaption).where(ClipCaption.clip_id == clip_id))


def _active_job(db: Session, clip: Clip, job_type: str):
    rows = db.scalars(
        select(Job).where(Job.type == job_type, Job.video_id == clip.video_id, Job.status.in_(["queued", "processing"]))
    ).all()
    for j in rows:
        try:
            if int(json.loads(j.payload or "{}").get("clip_id", -1)) == clip.id:
                return j
        except (ValueError, TypeError):
            continue
    return None


@router.post("/{clip_id}/captions/generate")
def generate_captions(clip_id: int, body: Optional[GenerateBody] = None, db: Session = Depends(get_db)):
    body = body or GenerateBody()
    clip = _ready_clip(db, clip_id)
    active = _active_job(db, clip, "caption_generate")
    if active:
        return {"job_id": active.id, "already_running": True}
    job = Job(type="caption_generate", video_id=clip.video_id, status="queued",
              payload=json.dumps({"clip_id": clip.id, "language": body.language}))
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"job_id": job.id, "already_running": False}


@router.get("/{clip_id}/captions")
def get_captions(clip_id: int, db: Session = Depends(get_db)):
    _clip_or_404(db, clip_id)
    row = _caption_row(db, clip_id)
    if row is None:
        raise HTTPException(404, "No captions yet. Generate them first.")
    lines = json.loads(row.lines_json or "[]")
    return {
        "clip_id": clip_id,
        "language": row.language,
        "updated_at": row.updated_at.isoformat(),
        "lines": [{"start": l["start"], "end": l["end"], "text": l["text"], "has_words": bool(l.get("words"))}
                  for l in lines],
    }


@router.put("/{clip_id}/captions")
def save_captions(clip_id: int, body: SaveBody, db: Session = Depends(get_db)):
    _clip_or_404(db, clip_id)
    row = _caption_row(db, clip_id)
    if row is None:
        raise HTTPException(404, "No captions yet. Generate them first.")
    if len(body.lines) > MAX_LINES:
        raise HTTPException(422, f"At most {MAX_LINES} caption lines")
    old = json.loads(row.lines_json or "[]")
    new = []
    for i, l in enumerate(body.lines):
        text = " ".join(l.text.split())
        if not text:
            raise HTTPException(422, f"Line {i + 1} is empty. Remove the text only by deleting the line.")
        if l.end <= l.start:
            raise HTTPException(422, f"Line {i + 1}: end must be after start")
        item = {"start": round(l.start, 2), "end": round(l.end, 2), "text": text}
        if i < len(old) and old[i].get("words") and old[i]["text"] == text \
                and abs(old[i]["start"] - item["start"]) < 0.05 and abs(old[i]["end"] - item["end"]) < 0.05:
            item["words"] = old[i]["words"]  # unchanged line keeps word timing (for the highlight style)
        new.append(item)
    row.lines_json = json.dumps(new, ensure_ascii=False)
    db.commit()
    return {"saved": True, "lines": len(new)}


@router.get("/{clip_id}/captions.srt")
def download_srt(clip_id: int, db: Session = Depends(get_db)):
    clip = _clip_or_404(db, clip_id)
    row = _caption_row(db, clip_id)
    if row is None:
        raise HTTPException(404, "No captions yet. Generate them first.")
    safe = re.sub(r"[^\w\-. ()]+", "_", clip.title).strip(" .") or "captions"
    return PlainTextResponse(
        to_srt(json.loads(row.lines_json or "[]")), media_type="application/x-subrip",
        headers={"Content-Disposition": f'attachment; filename="{safe}.srt"'},
    )


@router.post("/{clip_id}/captions/burn")
def burn(clip_id: int, body: Optional[BurnBody] = None, db: Session = Depends(get_db)):
    body = body or BurnBody()
    clip = _ready_clip(db, clip_id)
    row = _caption_row(db, clip_id)
    if row is None or not json.loads(row.lines_json or "[]"):
        raise HTTPException(400, "This clip has no captions to burn in. Generate them first.")
    if not has_subtitles_filter():
        raise HTTPException(400, "This FFmpeg build has no subtitles (libass) support. Install a full FFmpeg build.")
    new = Clip(video_id=clip.video_id, title=f"{clip.title} (captions)"[:200], start_sec=clip.start_sec,
               end_sec=clip.end_sec, duration_sec=clip.duration_sec, ai_score=clip.ai_score, status="pending")
    db.add(new)
    db.flush()
    job = Job(type="caption_burn", video_id=clip.video_id, status="queued",
              payload=json.dumps({"clip_id": clip.id, "new_clip_id": new.id, "style": body.style,
                                  "position": body.position, "font_size": body.font_size}))
    db.add(job)
    db.commit()
    db.refresh(new)
    db.refresh(job)
    return {"clip": clip_dict(new), "clip_id": new.id, "job_id": job.id}