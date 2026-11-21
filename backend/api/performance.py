from typing import Literal

import psutil
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services import performance as perf

router = APIRouter(prefix="/api/performance", tags=["performance"])


class PerfBody(BaseModel):
    low_memory: bool
    frame_width: Literal[256, 320, 384, 512] = 384


class CleanBody(BaseModel):
    target: str  # stale_temporary | music_peaks


@router.get("")
def get_performance():
    mem = psutil.virtual_memory()
    s = perf.load()
    total_gb = round(mem.total / 1024**3, 1)
    return {
        "settings": s,
        "effective": perf.effective(),
        "ram": {"total_gb": total_gb, "available_gb": round(mem.available / 1024**3, 1), "used_percent": mem.percent},
        "recommend_low_memory": bool(total_gb <= 9.5 and not s["low_memory"]),
        "stale_temporary_bytes": perf.stale_temporary_bytes(6.0),
        "music_peaks_bytes": perf.peaks_bytes(),
    }


@router.post("")
def set_performance(body: PerfBody):
    s = {"low_memory": body.low_memory, "frame_width": int(body.frame_width)}
    perf.save(s)
    perf.apply(s)
    return {"settings": s, "effective": perf.effective()}


@router.post("/cleanup")
def cleanup(body: CleanBody):
    if body.target == "stale_temporary":
        return {"target": body.target, **perf.clean_stale_temporary(6.0)}
    if body.target == "music_peaks":
        return {"target": body.target, **perf.clean_peaks()}
    raise HTTPException(400, "Unknown cleanup target")