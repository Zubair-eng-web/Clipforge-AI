from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.database.models import Clip, Video, VideoAnalysis
from backend.services.paths import resolve_storage


def _unlink_rel(rel):
    if not rel:
        return
    try:
        resolve_storage(rel).unlink(missing_ok=True)
    except (ValueError, OSError):
        pass


def delete_clip_files(clip: Clip) -> None:
    _unlink_rel(clip.file_path)
    _unlink_rel(clip.thumbnail_path)


def cleanup_video_files(db: Session, video: Video) -> None:
    """Delete generated clips + preview proxy files of a video (DB rows go via FK cascade)."""
    for clip in db.scalars(select(Clip).where(Clip.video_id == video.id)).all():
        delete_clip_files(clip)
    _unlink_rel(video.proxy_path)
    db.execute(delete(VideoAnalysis).where(VideoAnalysis.video_id == video.id))
