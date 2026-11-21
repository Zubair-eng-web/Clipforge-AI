r"""Timing + peak RAM benchmark for CLIPFORGE AI (Phase 9 pending test, run in 12.12).

The backend must be running (.\scripts\start-all.ps1). Do not run other jobs at the same time.
It uses a video that is already uploaded (pick a 2-5 minute one with speech).

  .\.venv\Scripts\python.exe scripts\benchmark.py                 (shortest video of 60 s or more)
  .\.venv\Scripts\python.exe scripts\benchmark.py --video-id 3
  .\.venv\Scripts\python.exe scripts\benchmark.py --video-id 3 --gaming
  .\.venv\Scripts\python.exe scripts\benchmark.py --gemini        (also times Gemini scoring / frames)

Writes (appends) PERFORMANCE_REPORT.md in the project root.
NOTE: the transcript of that video is redone (force), so its old transcript is replaced."""
import argparse
import datetime
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import psutil

API = os.getenv("CLIPFORGE_API", "http://localhost:8000")
ROOT = Path(__file__).resolve().parents[1]
TERMINAL = ("completed", "failed", "cancelled")


def call(method, path, body=None, timeout=60):
    data, headers = None, {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"{method} {path} -> {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach the backend at {API}: {e.reason}. Start it with .\\scripts\\start-all.ps1")


def backend_procs(port):
    """Backend process + its children, as {pid: psutil.Process}."""
    pids = set()
    try:
        for c in psutil.net_connections(kind="tcp"):
            if c.status == "LISTEN" and c.laddr and c.laddr.port == port and c.pid:
                pids.add(c.pid)
    except (psutil.AccessDenied, OSError):
        pass
    if not pids:
        for p in psutil.process_iter(["pid", "cmdline"]):
            cl = " ".join(p.info.get("cmdline") or [])
            if "uvicorn" in cl and "backend.main" in cl:
                pids.add(p.info["pid"])
    procs = {}
    for pid in pids:
        try:
            p = psutil.Process(pid)
            procs[pid] = p
            for c in p.children(recursive=True):
                procs[c.pid] = c
        except psutil.Error:
            continue
    return procs


def rss_mb(procs):
    total = 0
    for p in list(procs.values()):
        try:
            total += p.memory_info().rss
        except psutil.Error:
            continue
    return total / 1024 ** 2


class Sampler(threading.Thread):
    """Samples backend RAM (RSS) and system free RAM every 0.5 s."""

    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self.stop_flag = threading.Event()
        self.phase = "idle"
        self.peaks = {}
        self.peak = 0.0
        self.min_avail = psutil.virtual_memory().available / 1024 ** 3
        self.found = False

    def run(self):
        while not self.stop_flag.is_set():
            procs = backend_procs(self.port)
            self.found = self.found or bool(procs)
            mb = rss_mb(procs)
            self.peaks[self.phase] = max(self.peaks.get(self.phase, 0.0), mb)
            self.peak = max(self.peak, mb)
            self.min_avail = min(self.min_avail, psutil.virtual_memory().available / 1024 ** 3)
            self.stop_flag.wait(0.5)

    def stop(self):
        self.stop_flag.set()
        self.join(timeout=3)


def wait_job(job_id, timeout):
    end = time.time() + timeout
    while time.time() < end:
        j = call("GET", f"/api/jobs/{job_id}")
        if j["status"] in TERMINAL:
            return j
        time.sleep(1.0)
    call("POST", f"/api/jobs/{job_id}/cancel")
    return {"status": "timeout", "error": f"Did not finish within {timeout} s (job cancelled)"}


def realtime_factor(video_sec, seconds):
    """How many seconds of video are handled per second of work (higher = faster)."""
    if not seconds or seconds <= 0 or not video_sec:
        return None
    return round(float(video_sec) / float(seconds), 2)


def fmt_report(res):
    v = res["video"]
    lines = [
        f"## Run {res['when']}",
        "",
        f"- Video: #{v['id']} {v['name']} ({v['duration']:.0f} s)",
        f"- PC RAM: {res['ram_total_gb']} GB total, lowest free during the run: {res['min_avail_gb']:.1f} GB",
        f"- Whisper model: {res['whisper']}, low-memory mode: {'ON' if res['low_memory'] else 'off'}, "
        f"frame width: {res['frame_width']} px, Gemini: {'on' if res['gemini'] else 'off'}",
        f"- Backend peak RAM: {res['peak_mb']:.0f} MB" + ("" if res["found"] else " (backend process not found, value is 0)"),
        "",
        "| Step | Result | Seconds | Video s per work s | Backend peak RAM (MB) |",
        "|---|---|---|---|---|",
    ]
    for s in res["steps"]:
        rf = realtime_factor(v["duration"], s["seconds"])
        lines.append(f"| {s['name']} | {s['status']} | {s['seconds']:.1f} | {rf if rf is not None else '-'} | {s['peak_mb']:.0f} |")
    errs = [f"- {s['name']}: {s['error']}" for s in res["steps"] if s.get("error")]
    if errs:
        lines += ["", "Errors:"] + errs
    lines += ["", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-id", type=int, default=0)
    ap.add_argument("--gemini", action="store_true", help="use Gemini for highlight scoring")
    ap.add_argument("--gaming", action="store_true", help="also time a Gaming Highlights run (3 categories)")
    ap.add_argument("--vision", action="store_true", help="gaming run: send small frames to Gemini")
    ap.add_argument("--timeout", type=int, default=3600, help="max seconds per step")
    a = ap.parse_args()

    call("GET", "/api/health")
    busy = call("GET", "/api/jobs?status=processing&limit=5")["items"] + call("GET", "/api/jobs?status=queued&limit=5")["items"]
    if busy:
        print("Other jobs are running or waiting. Wait until the queue is empty, then run again.")
        return 2

    videos = [v for v in call("GET", "/api/videos?limit=500")["items"] if v.get("has_video")]
    if a.video_id:
        pick = [v for v in videos if v["id"] == a.video_id]
    else:
        pick = sorted([v for v in videos if (v.get("duration_sec") or 0) >= 60], key=lambda v: v["duration_sec"])[:1]
    if not pick:
        print("No suitable video found. Upload a 2-5 minute video with speech first (or pass --video-id).")
        return 2
    v = pick[0]
    vid, vdur = v["id"], float(v.get("duration_sec") or 0)
    if vdur > 900:
        print(f"Warning: this video is {vdur / 60:.0f} minutes long. On 8 GB RAM this can take very long.")

    try:
        perf = call("GET", "/api/performance")
    except RuntimeError:
        perf = {"settings": {"low_memory": False, "frame_width": 384}}
    status = call("GET", "/api/analysis/status")
    port = urlparse(API).port or 8000

    s = Sampler(port)
    s.start()
    steps = []

    def step(name, start_fn):
        s.phase = name
        t0 = time.time()
        r = start_fn()
        if r.get("already_running"):
            return {"name": name, "status": "skipped", "seconds": 0.0, "peak_mb": 0.0,
                    "error": "A job was already running for this video"}
        j = wait_job(r["job_id"], a.timeout)
        out = {"name": name, "status": j["status"], "seconds": time.time() - t0,
               "peak_mb": s.peaks.get(name, 0.0), "error": j.get("error")}
        print(f"  {name}: {out['status']} in {out['seconds']:.1f} s, backend peak {out['peak_mb']:.0f} MB")
        return out

    def analysis(steps_list, use_gemini, force):
        return lambda: call("POST", f"/api/analysis/videos/{vid}/run",
                            {"steps": steps_list, "use_gemini": use_gemini, "force": force})

    print(f"Video #{vid} {v['name']} ({vdur:.0f} s). Backend on port {port}.")
    try:
        for name, lst, gem, force in (("1 Whisper transcript", ["transcribe"], False, True),
                                      ("2 Scene detection", ["scenes"], False, False),
                                      ("3 Highlight scoring", ["highlights"], a.gemini, False)):
            r = step(name, analysis(lst, gem, force))
            steps.append(r)
            if r["status"] != "completed":
                break
        if a.gaming and all(x["status"] == "completed" for x in steps):
            cats = [c["key"] for c in call("GET", "/api/gaming/categories")["items"] if c["key"] != "custom"][:3]
            body = {"categories": [{"key": k, "custom_text": "", "duration": "auto"} for k in cats],
                    "options": {"use_vision": bool(a.vision), "use_speech": True, "auto_extract": False}}
            steps.append(step("4 Gaming highlights" + (" (with frames)" if a.vision else " (audio + speech)"),
                              lambda: call("POST", f"/api/gaming/videos/{vid}/run", body)))
    finally:
        s.stop()

    res = {
        "when": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "video": {"id": vid, "name": v["name"], "duration": vdur},
        "ram_total_gb": round(psutil.virtual_memory().total / 1024 ** 3, 1),
        "min_avail_gb": s.min_avail,
        "whisper": status.get("whisper_model", "?"),
        "low_memory": bool(perf["settings"].get("low_memory")),
        "frame_width": perf["settings"].get("frame_width", 384),
        "gemini": bool(a.gemini),
        "peak_mb": s.peak,
        "found": s.found,
        "steps": steps,
    }
    report = ROOT / "PERFORMANCE_REPORT.md"
    head = "" if report.exists() else "# CLIPFORGE AI performance report\n\nEach run is appended below. Compare runs with low-memory mode on and off.\n\n"
    with open(report, "a", encoding="utf-8") as f:
        f.write(head + fmt_report(res))
    print(f"\nReport written: {report}")
    return 0 if all(x["status"] == "completed" for x in steps) else 1


if __name__ == "__main__":
    sys.exit(main())