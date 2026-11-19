"""SQLite-backed job queue with background worker threads (default 1 worker for 8GB RAM)."""
import json
import logging
import os
import threading
import time

from sqlalchemy import select, update

from backend.database.db import SessionLocal
from backend.database.models import Clip, Job, utcnow

log = logging.getLogger("clipforge.runner")

HANDLERS = {}
_stop = threading.Event()
_threads: list = []


class JobCancelled(Exception):
    pass


def register(job_type: str):
    def deco(fn):
        HANDLERS[job_type] = fn
        return fn
    return deco


class JobContext:
    def __init__(self, job_id: int, payload: dict):
        self.job_id = job_id
        self.payload = payload
        self._t = 0.0

    def progress(self, p: float) -> None:
        """p is 0.0..1.0. Writes to DB at most once per second and checks for cancellation."""
        now = time.monotonic()
        if now - self._t < 1.0 and p < 1.0:
            return
        self._t = now
        with SessionLocal() as db:
            status = db.scalar(select(Job.status).where(Job.id == self.job_id))
            if status == "cancelled":
                raise JobCancelled()
            db.execute(
                update(Job)
                .where(Job.id == self.job_id, Job.status == "processing")
                .values(progress=round(min(max(p, 0.0), 1.0) * 100, 1), updated_at=utcnow())
            )
            db.commit()


def _claim():
    with SessionLocal() as db:
        row = db.execute(
            select(Job.id, Job.type, Job.payload).where(Job.status == "queued").order_by(Job.id).limit(1)
        ).first()
        if row is None:
            return None
        res = db.execute(
            update(Job).where(Job.id == row.id, Job.status == "queued")
            .values(status="processing", progress=0.0, updated_at=utcnow())
        )
        db.commit()
        return row if res.rowcount == 1 else None


def _finish(job_id: int, status: str, error: str = None) -> None:
    vals = {"status": status, "updated_at": utcnow()}
    if status == "completed":
        vals["progress"] = 100.0
    if error:
        vals["error"] = error[:1000]
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.id == job_id, Job.status == "processing").values(**vals))
        db.commit()


def _worker(_idx: int) -> None:
    while not _stop.is_set():
        try:
            row = _claim()
        except Exception:
            log.exception("could not claim a job")
            _stop.wait(2)
            continue
        if row is None:
            _stop.wait(0.7)
            continue
        handler = HANDLERS.get(row.type)
        if handler is None:
            _finish(row.id, "failed", f"Unknown job type: {row.type}")
            continue
        try:
            payload = json.loads(row.payload) if row.payload else {}
            handler(JobContext(row.id, payload))
            _finish(row.id, "completed")
        except JobCancelled:
            pass  # status already set to cancelled by the API
        except Exception as e:
            log.exception("job %s failed", row.id)
            _finish(row.id, "failed", str(e) or e.__class__.__name__)


def _recover_interrupted() -> None:
    with SessionLocal() as db:
        db.execute(update(Job).where(Job.status == "processing")
                   .values(status="failed", error="Interrupted (server restarted)", updated_at=utcnow()))
        db.execute(update(Clip).where(Clip.status == "processing").values(status="failed"))
        db.commit()


def start() -> None:
    global _threads
    from backend.workers import handlers  # noqa: F401  (registers job handlers)
    if any(t.is_alive() for t in _threads):
        return
    _recover_interrupted()
    _stop.clear()
    n = min(max(int(os.getenv("MAX_CONCURRENT_JOBS", "1") or 1), 1), 4)
    _threads = [threading.Thread(target=_worker, args=(i,), name=f"clipforge-worker-{i}", daemon=True)
                for i in range(n)]
    for t in _threads:
        t.start()


def stop() -> None:
    _stop.set()
    for t in _threads:
        t.join(timeout=5)
