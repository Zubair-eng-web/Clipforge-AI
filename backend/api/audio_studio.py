import mimetypes
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import config
from backend.api.clips import clip_dict
from backend.audio_studio.suggest import suggest_tracks
from backend.audio_studio.waveform import compute_peaks
from backend.database.db import get_db
from backend.database.models import CategoryScene, Clip, Job, MusicCollection, MusicCollectionTrack, MusicTrack
from backend.editor.ops import has_audio
from backend.services.paths import resolve_storage
from backend.video_processing.ffprobe import ProbeError, probe

music_router = APIRouter(prefix="/api/music", tags=["music"])
mcol_router = APIRouter(prefix="/api/music-collections", tags=["music"])
studio_router = APIRouter(prefix="/api/audio-studio", tags=["audio-studio"])
CHUNK = 1024 * 1024


# ---------- helpers ----------
def _clean(s: str, n: int) -> str:
    return re.sub(r"[\x00-\x1f]", "", s or "").strip()[:n]


def track_dict(t: MusicTrack) -> dict:
    return {"id": t.id, "name": t.name, "original_name": t.original_name, "folder": t.folder, "tags": t.tags,
            "duration_sec": t.duration_sec, "size_bytes": t.size_bytes, "created_at": t.created_at.isoformat()}


def _track(db: Session, tid: int) -> MusicTrack:
    t = db.get(MusicTrack, tid)
    if not t:
        raise HTTPException(404, "Music track not found")
    return t


def _track_file(t: MusicTrack) -> Path:
    try:
        p = resolve_storage(t.file_path)
    except ValueError:
        raise HTTPException(400, "Invalid stored path")
    if not p.is_file():
        raise HTTPException(404, "Music file is missing on disk")
    return p


def _peaks_path(tid: int) -> Path:
    return config.STORAGE_DIR / "music" / "peaks" / f"{tid}.json"


# ---------- music library ----------
@music_router.post("/upload")
def upload(files: List[UploadFile] = File(...), folder: str = Form(""), db: Session = Depends(get_db)):
    folder = _clean(folder, 100)
    music_dir = config.STORAGE_DIR / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    (config.STORAGE_DIR / "temporary").mkdir(parents=True, exist_ok=True)
    limit = int(float(os.getenv("MAX_MUSIC_MB", "300")) * 1024 * 1024)
    uploaded, errors = [], []
    for f in files:
        tmp = config.STORAGE_DIR / "temporary" / f"{uuid.uuid4().hex}.part"
        try:
            display = config.safe_display_name(f.filename or "")
            ext = re.sub(r"[^a-z0-9]", "", Path(display).suffix.lower())[:5] or "audio"
            size = 0
            with open(tmp, "wb") as out:
                while True:
                    chunk = f.file.read(CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > limit:
                        raise ValueError("File is larger than the music upload limit (MAX_MUSIC_MB in .env)")
                    out.write(chunk)
            if size == 0:
                raise ValueError("File is empty")
            try:
                info = probe(tmp)
            except ProbeError as e:
                raise ValueError(str(e))
            if not has_audio(tmp):
                raise ValueError("This file has no audio")
            final = f"{uuid.uuid4().hex}.{ext}"
            shutil.move(str(tmp), str(music_dir / final))
            t = MusicTrack(name=Path(display).stem[:300] or "Track", original_name=display, file_path=f"music/{final}",
                           size_bytes=size, duration_sec=info["duration_sec"], folder=folder)
            db.add(t)
            db.commit()
            db.refresh(t)
            uploaded.append(track_dict(t))
        except ValueError as e:
            errors.append({"filename": f.filename, "error": str(e)})
        finally:
            tmp.unlink(missing_ok=True)
    return {"uploaded": uploaded, "errors": errors}


@music_router.get("")
def list_tracks(folder: str = "", q: str = "", collection_id: int = 0, limit: int = 500, db: Session = Depends(get_db)):
    stmt = select(MusicTrack)
    if folder:
        stmt = stmt.where(MusicTrack.folder == folder)
    if q.strip():
        stmt = stmt.where(MusicTrack.name.contains(q.strip(), autoescape=True))
    if collection_id:
        ids = db.scalars(select(MusicCollectionTrack.track_id).where(MusicCollectionTrack.collection_id == collection_id)).all()
        stmt = stmt.where(MusicTrack.id.in_(ids))
    rows = db.scalars(stmt.order_by(MusicTrack.id.desc()).limit(min(max(limit, 1), 1000))).all()
    folders = sorted({f for f in db.scalars(select(MusicTrack.folder)).all() if f})
    return {"items": [track_dict(t) for t in rows], "folders": folders}


class TrackPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=300)
    folder: Optional[str] = Field(default=None, max_length=100)
    tags: Optional[str] = Field(default=None, max_length=500)


@music_router.patch("/{tid}")
def patch_track(tid: int, body: TrackPatch, db: Session = Depends(get_db)):
    t = _track(db, tid)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        t.name = _clean(data["name"], 300) or t.name
    if "folder" in data and data["folder"] is not None:
        t.folder = _clean(data["folder"], 100)
    if "tags" in data and data["tags"] is not None:
        t.tags = _clean(data["tags"], 500)
    db.commit()
    return track_dict(t)


@music_router.delete("/{tid}")
def delete_track(tid: int, db: Session = Depends(get_db)):
    t = _track(db, tid)
    try:
        resolve_storage(t.file_path).unlink(missing_ok=True)
    except (ValueError, OSError):
        pass
    _peaks_path(tid).unlink(missing_ok=True)
    db.delete(t)  # clips that already used this track keep their mixed audio
    db.commit()
    return {"deleted": tid}


_TYPES = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".aac": "audio/aac", ".flac": "audio/flac",
          ".ogg": "audio/ogg", ".opus": "audio/ogg"}


@music_router.get("/{tid}/stream")
def stream_track(tid: int, db: Session = Depends(get_db)):
    p = _track_file(_track(db, tid))
    return FileResponse(p, media_type=_TYPES.get(p.suffix.lower()) or mimetypes.guess_type(p.name)[0] or "audio/mpeg")


@music_router.get("/{tid}/waveform")
def waveform(tid: int, db: Session = Depends(get_db)):
    t = _track(db, tid)
    import json
    cache = _peaks_path(tid)
    if cache.is_file():
        try:
            return {"peaks": json.loads(cache.read_text(encoding="utf-8"))}
        except ValueError:
            pass
    peaks = compute_peaks(_track_file(t), t.duration_sec or 0.0)
    if peaks:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(peaks), encoding="utf-8")
    return {"peaks": peaks}


# ---------- collections ----------
class ColIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TrackIds(BaseModel):
    track_ids: List[int] = Field(min_length=1, max_length=200)


def _col(c: MusicCollection, db: Session) -> dict:
    ids = db.scalars(select(MusicCollectionTrack.track_id).where(MusicCollectionTrack.collection_id == c.id)).all()
    return {"id": c.id, "name": c.name, "track_ids": list(ids), "track_count": len(ids)}


@mcol_router.get("")
def list_cols(db: Session = Depends(get_db)):
    return {"items": [_col(c, db) for c in db.scalars(select(MusicCollection).order_by(MusicCollection.id.desc())).all()]}


@mcol_router.post("")
def create_col(body: ColIn, db: Session = Depends(get_db)):
    c = MusicCollection(name=_clean(body.name, 200) or "Collection")
    db.add(c)
    db.commit()
    db.refresh(c)
    return _col(c, db)


@mcol_router.delete("/{cid}")
def delete_col(cid: int, db: Session = Depends(get_db)):
    c = db.get(MusicCollection, cid)
    if not c:
        raise HTTPException(404, "Collection not found")
    db.delete(c)  # tracks stay in the library
    db.commit()
    return {"deleted": cid}


@mcol_router.post("/{cid}/tracks")
def col_add(cid: int, body: TrackIds, db: Session = Depends(get_db)):
    if not db.get(MusicCollection, cid):
        raise HTTPException(404, "Collection not found")
    have = set(db.scalars(select(MusicCollectionTrack.track_id).where(MusicCollectionTrack.collection_id == cid)).all())
    added = 0
    for tid in dict.fromkeys(body.track_ids):
        if tid in have or db.get(MusicTrack, tid) is None:
            continue
        db.add(MusicCollectionTrack(collection_id=cid, track_id=tid))
        added += 1
    db.commit()
    return {"added": added}


@mcol_router.delete("/{cid}/tracks/{tid}")
def col_remove(cid: int, tid: int, db: Session = Depends(get_db)):
    row = db.scalar(select(MusicCollectionTrack).where(MusicCollectionTrack.collection_id == cid, MusicCollectionTrack.track_id == tid))
    if not row:
        raise HTTPException(404, "Track is not in this collection")
    db.delete(row)
    db.commit()
    return {"removed": tid}


# ---------- audio studio ----------
class TrackIn(BaseModel):
    track_id: int
    volume: float = Field(50, ge=0, le=100)
    start_sec: float = Field(0, ge=0)
    trim_in: float = Field(0, ge=0)
    trim_out: Optional[float] = Field(None, gt=0)
    fade_in: float = Field(0, ge=0, le=30)
    fade_out: float = Field(0, ge=0, le=30)
    loop: bool = False
    enabled: bool = True


class MixIn(BaseModel):
    original_enabled: bool = True
    original_volume: float = Field(100, ge=0, le=100)
    tracks: List[TrackIn] = Field(default_factory=list, max_length=6)
    codec: Literal["aac", "mp3", "opus"] = "aac"
    bitrate_kbps: int = Field(192, ge=64, le=320)
    title: str = Field("", max_length=200)


def _ready(db: Session, clip_id: int) -> Clip:
    c = db.get(Clip, clip_id)
    if not c:
        raise HTTPException(404, "Clip not found")
    if c.status != "ready" or not c.file_path:
        raise HTTPException(409, "The clip is not ready yet")
    return c


def _settings(db: Session, clip: Clip, body: MixIn) -> dict:
    dur = float(clip.duration_sec or 0.0)
    tracks = []
    for t in body.tracks:
        if not t.enabled or t.volume <= 0:
            continue
        m = db.get(MusicTrack, t.track_id)
        if m is None:
            raise HTTPException(404, f"Music track {t.track_id} not found")
        if dur and t.start_sec >= dur - 0.05:
            raise HTTPException(400, "A music track starts after the end of the clip")
        td = float(m.duration_sec or 0.0)
        if t.trim_out is not None and t.trim_out <= t.trim_in:
            raise HTTPException(400, "Music trim end must be after trim start")
        if td and t.trim_in >= td - 0.05:
            raise HTTPException(400, "Music trim start is beyond the end of the track")
        tracks.append(t.model_dump())
    if not tracks:
        raise HTTPException(400, "Add at least one enabled music track with volume above 0")
    return {"original_enabled": body.original_enabled, "original_volume": body.original_volume, "tracks": tracks,
            "codec": body.codec, "bitrate_kbps": body.bitrate_kbps}


@studio_router.post("/clips/{clip_id}/mix")
def mix(clip_id: int, body: MixIn, db: Session = Depends(get_db)):
    clip = _ready(db, clip_id)
    settings = _settings(db, clip, body)
    new = Clip(video_id=clip.video_id, title=(body.title.strip() or f"{clip.title} (music)")[:200],
               start_sec=clip.start_sec, end_sec=clip.end_sec, duration_sec=clip.duration_sec, width=clip.width,
               height=clip.height, aspect_ratio=clip.aspect_ratio, ai_score=clip.ai_score, status="pending")
    db.add(new)
    db.flush()
    job = Job(type="audio_mix", video_id=clip.video_id, status="queued",
              payload=__import__("json").dumps({"clip_id": clip.id, "new_clip_id": new.id, "settings": settings}))
    db.add(job)
    db.commit()
    db.refresh(new)
    db.refresh(job)
    return {"clip": clip_dict(new), "clip_id": new.id, "job_id": job.id}


@studio_router.post("/clips/{clip_id}/preview")
def preview(clip_id: int, body: MixIn, seconds: float = 20, db: Session = Depends(get_db)):
    clip = _ready(db, clip_id)
    settings = _settings(db, clip, body)
    job = Job(type="audio_mix", video_id=clip.video_id, status="queued",
              payload=__import__("json").dumps({"clip_id": clip.id, "preview": True,
                                                "preview_seconds": min(max(seconds, 3), 60), "settings": settings}))
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"job_id": job.id}


@studio_router.get("/preview/{job_id}")
def preview_file(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j or j.type != "audio_mix" or j.status != "completed":
        raise HTTPException(404, "Preview is not ready")
    p = config.STORAGE_DIR / "previews" / f"audiomix_{job_id}.mp4"
    if not p.is_file():
        raise HTTPException(404, "Preview file is missing")
    return FileResponse(p, media_type="video/mp4")


class SuggestIn(BaseModel):
    clip_id: Optional[int] = None
    category: str = ""


@studio_router.post("/suggest")
def suggest(body: SuggestIn, db: Session = Depends(get_db)):
    cat = body.category.strip().lower()
    if not cat and body.clip_id:
        row = db.scalars(select(CategoryScene).where(CategoryScene.clip_id == body.clip_id)).first()
        cat = row.category if row else ""
    if not cat:
        raise HTTPException(400, "Choose a scene category first")
    tracks = [{"id": t.id, "name": t.name, "folder": t.folder, "tags": t.tags}
              for t in db.scalars(select(MusicTrack)).all()]
    if not tracks:
        return {"category": cat, "source": "none", "items": [], "message": "Your music library is empty. Upload your own tracks first."}
    items, source = suggest_tracks(cat, tracks)
    msg = "" if items else "No track in your library clearly matches. Add tags such as epic, soft, funny to your tracks."
    return {"category": cat, "source": source, "items": items, "message": msg}