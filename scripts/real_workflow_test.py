"""CLIPFORGE AI - live workflow test (Phase 12.12b).
Backend must be running. Standard library only (curl.exe is used for big uploads).
Example:
  python scripts/real_workflow_test.py --video-id 1 --music-file "E:/music/song.mp3"
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--base", default="http://localhost:8000")
ap.add_argument("--video-id", type=int, default=0, help="default: latest video that has picture")
ap.add_argument("--video-file", default="", help="upload this video first")
ap.add_argument("--music-file", default="", help="your own audio file for the music test")
ap.add_argument("--cats", default="", help="gaming categories, comma separated (default: first 3)")
ap.add_argument("--platform", default="")
ap.add_argument("--confidence", type=float, default=40)
ap.add_argument("--no-gemini", action="store_true")
ap.add_argument("--no-scene-ai", action="store_true")
ap.add_argument("--only", default="", help="run only steps whose name contains one of these words, e.g. reel,music,social")
ap.add_argument("--clip-id", type=int, default=0, help="with --only: clip to use (default: latest ready clip)")
ap.add_argument("--timeout", type=int, default=1800, help="seconds to wait for one job")
A = ap.parse_args()
BASE = A.base.rstrip("/")
CTX, RESULTS = {}, []


def call(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    except Exception as e:
        return 0, str(e)
    try:
        return code, json.loads(raw.decode("utf-8"))
    except ValueError:
        return code, raw[:200]


def probe(path, timeout=60):
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            r.read(2048)
            return r.status, {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}


def upload(path, field, file):
    out = subprocess.run(["curl.exe", "-sS", "-F", f"{field}=@{file}", BASE + path], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("curl.exe failed: " + out.stderr.strip())
    return json.loads(out.stdout)


def wait_job(job_id):
    t0, last = time.time(), None
    while time.time() - t0 < A.timeout:
        c, j = call("GET", f"/api/jobs/{job_id}")
        if c != 200 or not isinstance(j, dict):
            return {"status": "error", "error": f"HTTP {c}"}
        pr = j.get("progress")
        if isinstance(pr, (int, float)):
            pct = int(pr * 100) if pr <= 1 else int(pr)
            if pct // 20 != last:
                last = pct // 20
                print(f"      job {job_id}: {j['status']} {pct}%")
        if j["status"] in ("completed", "failed", "cancelled"):
            return j
        time.sleep(2)
    return {"status": "timeout", "error": f"no result after {A.timeout}s"}


def wait_clip(cid, tries=120):
    for _ in range(tries):
        c, d = call("GET", f"/api/clips/{cid}")
        if c == 200 and isinstance(d, dict) and d.get("status") in ("ready", "failed", "cancelled"):
            return d
        time.sleep(2)
    return {"status": "timeout"}


def run(name, fn):
    t0 = time.time()
    try:
        st, detail = fn()
    except Exception as e:
        st, detail = "FAIL", f"{type(e).__name__}: {e}"
    secs = round(time.time() - t0, 1)
    RESULTS.append((name, st, str(detail), secs))
    print(f"[{st:4}] {name} ({secs}s) - {str(detail)[:260]}")
    return st


def s_health():
    c, d = call("GET", "/api/health")
    return ("PASS" if c == 200 else "FAIL"), f"HTTP {c} {d}"


def s_gemini():
    c, d = call("GET", "/api/analysis/status")
    if c != 200:
        return "FAIL", f"HTTP {c}"
    ok = bool(d.get("gemini_configured"))
    CTX["gemini"] = ok
    msg = f"whisper={d.get('whisper_model')} gemini={ok} model={d.get('gemini_model')}"
    return ("PASS" if ok else "WARN"), msg + ("" if ok else " (no key: scenes will be uncertain)")


def s_video():
    vid = A.video_id
    if A.video_file:
        d = upload("/api/videos/upload", "files", A.video_file)
        if not d.get("uploaded"):
            return "FAIL", d.get("errors")
        vid = d["uploaded"][0]["id"]
    if not vid:
        c, d = call("GET", "/api/videos?limit=100")
        vids = [v for v in (d.get("items") or []) if v.get("has_video")] if c == 200 else []
        if not vids:
            return "FAIL", "no video with picture; use --video-file or upload in the UI"
        vid = vids[0]["id"]
    c, v = call("GET", f"/api/videos/{vid}")
    if c != 200:
        return "FAIL", f"video {vid} not found"
    if not v.get("has_video"):
        return "FAIL", "this file is audio only"
    CTX["vid"] = vid
    CTX["len0"] = probe(f"/api/videos/{vid}/stream")[1].get("content-length")
    return "PASS", f"id={vid} name={v.get('name')} duration={v.get('duration_sec')}s"


def s_analyze():
    vid = CTX["vid"]
    c, d = call("POST", f"/api/videos/{vid}/analyze", {"use_gemini": not A.no_gemini})
    if c != 200:
        return "FAIL", f"HTTP {c} {d}"
    j = wait_job(d["job_id"])
    if j["status"] != "completed":
        return "FAIL", f"job {j['status']}: {j.get('error')}"
    c, a = call("GET", f"/api/videos/{vid}/analysis?include_transcript=false")
    if c != 200:
        return "FAIL", f"HTTP {c}"
    info = (f"status={a.get('status')} lang={a.get('language')} segments={a.get('segment_count')} "
            f"scenes={len(a.get('scenes') or [])} highlights={len(a.get('highlights') or [])} source={a.get('scoring_source')}")
    if not a.get("scenes"):
        return "FAIL", info
    if not a.get("segment_count"):
        return "WARN", info + " (no speech found)"
    return "PASS", info


def s_gaming():
    vid = CTX["vid"]
    c, d = call("GET", "/api/gaming/categories")
    keys = [i["key"] for i in d.get("items", []) if i["key"] != "custom"] if c == 200 else []
    if not keys:
        return "FAIL", "no gaming categories"
    sel = [k.strip() for k in A.cats.split(",") if k.strip()] or keys[:3]
    body = {"categories": [{"key": k, "duration": "auto"} for k in sel],
            "options": {"confidence": A.confidence, "min_scene_sec": 5, "use_vision": not A.no_gemini,
                        "use_speech": True, "auto_extract": False}}
    c, d = call("POST", f"/api/gaming/videos/{vid}/run", body)
    if c != 200:
        return "FAIL", f"HTTP {c} {d}"
    j = wait_job(d["job_id"])
    if j["status"] != "completed":
        return "FAIL", f"job {j['status']}: {j.get('error')}"
    c, h = call("GET", f"/api/gaming/videos/{vid}/highlights")
    items = h.get("items", []) if c == 200 else []
    CTX["hi"] = items
    det = sum(1 for i in items if i["status"] == "detected")
    info = f"categories={sel} highlights={len(items)} detected={det} uncertain={len(items) - det}"
    warn = (h.get("info") or {}).get("warnings") if c == 200 else None
    if warn:
        info += f" warnings={warn}"
    if not items:
        return "WARN", info + " (nothing found: try --confidence 25 or other --cats)"
    th = [i for i in items if i.get("thumbnail_url")]
    if not th:
        return "WARN", info + " (no thumbnails)"
    code, _ = probe(th[0]["thumbnail_url"])
    return ("PASS" if code == 200 else "FAIL"), info + f" thumbnail HTTP {code}"


def s_extract():
    vid, items = CTX["vid"], CTX.get("hi") or []
    if not items:
        return "SKIP", "no highlights"
    pick = sorted(items, key=lambda i: i["status"] != "detected")[:2]
    ids = [i["id"] for i in pick]
    c, d = call("POST", f"/api/scene-ai/videos/{vid}/extract", {"scene_ids": ids, "mode": "accurate", "subtitles": False})
    if c != 200:
        return "FAIL", f"HTTP {c} {d}"
    rows = []
    for _ in range(A.timeout // 3):
        c, h = call("GET", f"/api/gaming/videos/{vid}/highlights")
        rows = [i for i in h.get("items", []) if i["id"] in ids] if c == 200 else []
        if rows and all(r["clip_status"] in ("ready", "failed", "cancelled") for r in rows):
            break
        time.sleep(3)
    ready = [r["clip_id"] for r in rows if r["clip_status"] == "ready"]
    CTX["clips"] = ready
    if not ready:
        return "FAIL", f"clip status: {[r['clip_status'] for r in rows]}"
    bad = []
    for cid in ready:
        c, k = call("GET", f"/api/clips/{cid}")
        code, _ = probe(f"/api/clips/{cid}/stream")
        if code != 200 or not (k.get("duration_sec") if isinstance(k, dict) else None):
            bad.append(cid)
    st = "FAIL" if bad else ("PASS" if len(ready) == len(ids) else "WARN")
    return st, f"requested={len(ids)} ready={len(ready)} unplayable={bad}"


def s_reel():
    if not CTX.get("clips"):
        return "SKIP", "no clip"
    src = CTX["clips"][0]
    plat = A.platform
    if not plat:
        c, p = call("GET", "/api/reels-studio/platforms")
        print("      platforms reply:", str(p)[:300])
        lst = p
        for _k in ("platforms", "items"):
            if isinstance(lst, dict) and _k in lst:
                lst = lst[_k]
        if isinstance(lst, dict):
            lst = [{"id": k} for k in lst]
        if isinstance(lst, list) and lst and isinstance(lst[0], dict):
            plat = lst[0].get("id") or lst[0].get("key") or lst[0].get("platform") or ""
        plat = plat or "youtube_shorts"
    body = {"clip_id": src, "platform": plat, "ratio": "9:16", "size": "720", "mode": "center",
            "target_sec": 15, "title": "REALTEST reel"}
    c, d = call("POST", "/api/reels-studio/create", body)
    if c != 200:
        return "FAIL", f"HTTP {c} {d}"
    new = d.get("clip_id") or (d.get("clip") or {}).get("id")
    if not new:
        return "FAIL", f"no clip id in response: {str(d)[:200]}"
    if d.get("job_id"):
        j = wait_job(d["job_id"])
        if j["status"] != "completed":
            return "FAIL", f"job {j['status']}: {j.get('error')}"
    k = wait_clip(new)
    if k.get("status") != "ready":
        return "FAIL", f"reel clip status {k.get('status')}"
    CTX["reel"] = new
    good = (k.get("width"), k.get("height")) == (720, 1280)
    return ("PASS" if good else "WARN"), f"platform={plat} clip={new} size={k.get('width')}x{k.get('height')} dur={k.get('duration_sec')}"


def s_music():
    src = CTX.get("reel") or (CTX.get("clips") or [None])[0]
    if not src:
        return "SKIP", "no clip"
    if not A.music_file:
        return "SKIP", "no --music-file given"
    if not Path(A.music_file).is_file():
        return "FAIL", "music file not found (use a real path): " + A.music_file
    d = upload("/api/music/upload", "files", A.music_file)
    if not d.get("uploaded"):
        return "FAIL", d.get("errors")
    tid = d["uploaded"][0]["id"]
    mix = {"original_enabled": True, "original_volume": 100, "codec": "aac", "bitrate_kbps": 192,
           "title": "REALTEST music",
           "tracks": [{"track_id": tid, "volume": 40, "loop": True, "fade_in": 1, "fade_out": 1}]}
    c, p = call("POST", f"/api/audio-studio/clips/{src}/preview?seconds=8", mix)
    if c != 200:
        return "FAIL", f"preview HTTP {c} {p}"
    j = wait_job(p["job_id"])
    pc, _ = probe(f"/api/audio-studio/preview/{p['job_id']}")
    if j["status"] != "completed" or pc != 200:
        return "FAIL", f"preview job {j['status']} file HTTP {pc} {j.get('error')}"
    c, d = call("POST", f"/api/audio-studio/clips/{src}/mix", mix)
    if c != 200:
        return "FAIL", f"mix HTTP {c} {d}"
    j = wait_job(d["job_id"])
    k = wait_clip(d["clip_id"])
    c, s = call("GET", f"/api/clips/{src}")
    if k.get("status") != "ready":
        return "FAIL", f"mixed clip status {k.get('status')} {j.get('error')}"
    same = abs(float(k.get("duration_sec") or 0) - float(s.get("duration_sec") or 0)) <= 0.6
    return ("PASS" if same else "FAIL"), f"preview HTTP {pc}; mixed clip {d['clip_id']} dur {k.get('duration_sec')} vs source {s.get('duration_sec')}"


def s_suggest():
    src = (CTX.get("clips") or [None])[0]
    if not src:
        return "SKIP", "no clip"
    c, d = call("POST", "/api/audio-studio/suggest", {"clip_id": src, "category": "fighting"})
    if c == 200:
        return "PASS", f"category={d.get('category')} source={d.get('source')} items={len(d.get('items') or [])} {d.get('message') or ''}"
    return "FAIL", f"HTTP {c} {d}"


def s_captions():
    src = (CTX.get("clips") or [None])[0]
    if not src:
        return "SKIP", "no clip"
    c, d = call("POST", f"/api/clips/{src}/captions/generate", {})
    if c != 200:
        return "WARN", f"generate HTTP {c} {str(d)[:200]} (send me this line, payload may differ)"
    if isinstance(d, dict) and d.get("job_id"):
        j = wait_job(d["job_id"])
        if j["status"] != "completed":
            return "FAIL", f"job {j['status']}: {j.get('error')}"
    c, cap = call("GET", f"/api/clips/{src}/captions")
    n = len(cap.get("segments") or cap.get("lines") or []) if isinstance(cap, dict) else 0
    code = probe(f"/api/clips/{src}/captions.srt")[0] if n else 0
    c2, _ = call("GET", f"/api/clips/{src}/captions/presets")
    info = f"lines={n} srt HTTP {code} presets HTTP {c2}"
    if c2 != 200:
        return "FAIL", info
    if not n:
        return "WARN", info + " (no speech in this clip = no captions, that is correct)"
    return ("PASS" if code == 200 else "FAIL"), info


def s_social():
    src = (CTX.get("clips") or [None])[0]
    if not src:
        return "SKIP", "no clip"
    plat = ""
    c, o = call("GET", "/api/social/options")
    if c == 200 and isinstance(o, dict):
        pl = o.get("platforms") or []
        pl = list(pl) if isinstance(pl, dict) else pl
        if pl:
            plat = pl[0] if isinstance(pl[0], str) else (pl[0].get("id") or pl[0].get("key") or "")
    c, d = call("POST", "/api/social/generate", {"clip_id": src, "tone": "viral", "platform": plat, "notes": ""})
    if c != 200 or not isinstance(d, dict) or not d:
        return "FAIL", f"HTTP {c} {str(d)[:200]}"
    return "PASS", f"HTTP 200 fields={sorted(d.keys())}"


def s_scene_ai():
    vid = CTX["vid"]
    c, d = call("GET", "/api/scene-ai/categories")
    keys = [i["key"] for i in d.get("items", []) if i["key"] != "custom"][:2] if c == 200 else []
    if not keys:
        return "FAIL", "no scene categories"
    body = {"categories": [{"key": k, "duration": "auto"} for k in keys],
            "options": {"confidence": A.confidence, "min_scene_sec": 5, "use_vision": not A.no_gemini,
                        "auto_extract": False}}
    c, d = call("POST", f"/api/scene-ai/videos/{vid}/run", body)
    if c != 200:
        return "FAIL", f"HTTP {c} {d}"
    j = wait_job(d["job_id"])
    if j["status"] != "completed":
        return "FAIL", f"job {j['status']}: {j.get('error')}"
    c, s = call("GET", f"/api/scene-ai/videos/{vid}/scenes")
    items = s.get("items", []) if c == 200 else []
    info = f"categories={keys} scenes={len(items)}"
    if not items:
        return "WARN", info + " (nothing found: try --confidence 25)"
    row = sorted(items, key=lambda r: r["status"] != "detected")[0]
    sid = row["id"]
    c, e = call("POST", f"/api/scene-ai/videos/{vid}/extract", {"scene_ids": [sid], "mode": "accurate", "subtitles": False})
    if c != 200:
        return "FAIL", info + f" extract HTTP {c} {e}"
    for _ in range(A.timeout // 3):
        c, s = call("GET", f"/api/scene-ai/videos/{vid}/scenes")
        row = next((r for r in s.get("items", []) if r["id"] == sid), row)
        if row.get("clip_status") in ("ready", "failed", "cancelled"):
            break
        time.sleep(3)
    good = row.get("clip_status") == "ready" and row.get("verified") is not False
    return ("PASS" if good else "FAIL"), info + f" clip={row.get('clip_status')} verified={row.get('verified')} file={row.get('filename')}"


PATHS = ["/api/health", "/api/dashboard", "/api/studio/stats", "/api/about", "/api/videos", "/api/clips", "/api/jobs",
         "/api/history", "/api/queue/summary", "/api/projects", "/api/collections", "/api/storage-manager/overview",
         "/api/analytics", "/api/diagnostics", "/api/settings", "/api/music", "/api/music-collections", "/api/reels",
         "/api/performance", "/api/gemini-key/status", "/api/batch/jobs", "/api/thumbnails"]


def s_regress():
    bad = []
    for p in PATHS:
        c, _ = call("GET", p, timeout=120)
        if c != 200:
            bad.append(f"{p}={c}")
    return ("FAIL" if bad else "PASS"), (f"{len(PATHS)} endpoints OK" if not bad else "failed: " + ", ".join(bad))


def s_untouched():
    code, h = probe(f"/api/videos/{CTX['vid']}/stream")
    a, b = CTX.get("len0"), h.get("content-length")
    if not a or not b:
        return "WARN", "no content-length header"
    return ("PASS" if a == b else "FAIL"), f"file size before {a} after {b}"


NO_VIDEO = {"Backend health", "Gemini / Whisper status", "Pick or upload video", "Old features still answer (regression)"}


def main():
    steps = [("Backend health", s_health), ("Gemini / Whisper status", s_gemini), ("Pick or upload video", s_video),
             ("AI analysis (transcript, scenes, highlights)", s_analyze),
             ("12.3 Gaming highlights + thumbnails", s_gaming), ("12.3 Extract gaming clips", s_extract),
             ("12.5 Reel from clip", s_reel), ("11.5 Music preview + mix", s_music),
             ("11.3 Music suggestions", s_suggest), ("12.4 Captions", s_captions), ("12.7 Social text", s_social)]
    if not A.no_scene_ai:
        steps.append(("10.4 Scene Detection categories", s_scene_ai))
    steps += [("Old features still answer (regression)", s_regress), ("Original video untouched", s_untouched)]
    if A.only:
        want = [w.strip().lower() for w in A.only.split(",") if w.strip()]
        steps = [s for s in steps if s[0] in ("Backend health", "Pick or upload video") or any(w in s[0].lower() for w in want)]
        if A.clip_id:
            CTX["clips"] = [A.clip_id]
        else:
            c, d = call("GET", "/api/clips?limit=50")
            lst = d.get("items", []) if isinstance(d, dict) else (d if isinstance(d, list) else [])
            rd = [k["id"] for k in lst if isinstance(k, dict) and k.get("status") == "ready"]
            if rd:
                CTX["clips"] = [rd[0]]
    for name, fn in steps:
        if name not in NO_VIDEO and "vid" not in CTX:
            RESULTS.append((name, "SKIP", "no video", 0))
            print(f"[SKIP] {name} - no video")
            continue
        st = run(name, fn)
        if name == "Backend health" and st == "FAIL":
            print("Backend is not running. Start it first: scripts/start-all.ps1")
            break
    lines = [f"\n## Real workflow test {datetime.now():%Y-%m-%d %H:%M}",
             f"Video id: {CTX.get('vid')}, Gemini key: {CTX.get('gemini')}\n",
             "| Step | Result | Seconds | Detail |", "|---|---|---|---|"]
    for n, s, d, t in RESULTS:
        lines.append(f"| {n} | {s} | {t} | {d[:160].replace('|', '/')} |")
    out = Path(__file__).resolve().parent.parent / "REAL_TEST_RESULT.md"
    with open(out, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    cnt = {k: sum(1 for r in RESULTS if r[1] == k) for k in ("PASS", "WARN", "FAIL", "SKIP")}
    print(f"\nSUMMARY: {cnt}  (saved to REAL_TEST_RESULT.md)")
    sys.exit(1 if cnt["FAIL"] else 0)


main()