from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import ForeignKey, String, Float, Integer, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[int] = mapped_column(primary_key=True)
    original_name: Mapped[str] = mapped_column(String(500))
    stored_path: Mapped[str] = mapped_column(String(1000))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    format: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="uploaded")
    proxy_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)  # browser preview copy (Phase 3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Clip(Base):
    __tablename__ = "clips"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(500), default="Untitled clip")
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    duration_sec: Mapped[float] = mapped_column(Float)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    aspect_ratio: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending/processing/ready/failed/cancelled
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    ai_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(50))
    video_id: Mapped[Optional[int]] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")  # queued/processing/completed/failed/cancelled
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # percent 0..100
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class VideoAnalysis(Base):
    """Result of the AI analysis of one video (transcript, scenes, highlights as JSON text)."""
    __tablename__ = "video_analysis"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="none")
    language: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    transcript_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scenes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    highlights_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scoring_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Transcript(Base):
    __tablename__ = "transcripts"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    language: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    language_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    segments: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of {start, end, text}
    model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Scene(Base):
    __tablename__ = "scenes"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)


class Highlight(Base):
    __tablename__ = "highlights"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    local_score: Mapped[float] = mapped_column(Float, default=0.0)
    title: Mapped[str] = mapped_column(String(300), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="local")  # local / gemini
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ClipCaption(Base):
    __tablename__ = "clip_captions"
    id: Mapped[int] = mapped_column(primary_key=True)
    clip_id: Mapped[int] = mapped_column(ForeignKey("clips.id", ondelete="CASCADE"), unique=True, index=True)
    language: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    lines_json: Mapped[str] = mapped_column(Text, default="[]")  # [{start, end, text, words?}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Thumbnail(Base):
    """A thumbnail made in Thumbnail Studio (file lives in storage/thumbnails/studio_*)."""
    __tablename__ = "thumbnails"
    id: Mapped[int] = mapped_column(primary_key=True)
    clip_id: Mapped[Optional[int]] = mapped_column(ForeignKey("clips.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    file_path: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    video_id: Mapped[Optional[int]] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CollectionClip(Base):
    __tablename__ = "collection_clips"
    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), index=True)
    clip_id: Mapped[int] = mapped_column(ForeignKey("clips.id", ondelete="CASCADE"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
