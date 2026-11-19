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
