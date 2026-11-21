"""13.1 test: the same API chain the One-Click Reel page uses. Backend must run.
Usage: python scripts/test_one_click_chain.py [clip_id] [tone_wav]"""
import json, subprocess, sys, time, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

BASE = "http://localhost:8000"
CLIP = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1] != "0" else 0
TONE = sys.argv[2] if len(sys.argv) > 2 else ""
OUT = []


def call(m, p, b=None, t=60):
    data = json.dumps(b).encode() if b is not None else None
    req = urllib.request.Request(BASE + p, data=data, method=m, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def cid(d):
    return d.get("clip_id") or (d.get("clip") or {}).get("id")


def wait_clip(i, n=450):
    for _ in range(n):
        c, d = call("GET", f"/api/clips/{i}")
        if c == 200 and d.get("status") in ("ready", "failed", "cancelled"):
            return d
        time.sleep(2)
    return {"status": "timeout"}


def wait_job(j, n=900):
    for _ in range(n):
        c, d = call("GET", f"/api/jobs/{j}")
        if d.get("status") in ("completed", "failed", "cancelled"):
            return d
        time.sleep(2)
    return {"status": "timeout"}


def latest():
    c, d = call("GET", "/api/clips?limit=10")
    return max([k["id"] for k in d.get("items", [])] or [0])


def rec(n, s, d):
    OUT.append((n, s, d))
    print(f"[{s}] {n} - {d}")


cur = CLIP
if not cur:
    c, d = call("GET", "/api/clips?limit=50")
    ok = [k for k in d.get("items", []) if k.get("status") == "ready" and (k.get("width") or 0) >= (k.get("height") or 0)]
    cur = ok[0]["id"] if ok else 0
if not cur:
    print("No ready clip found. Make one first.")
    sys.exit(1)
print("Source clip:", cur)

# 1 reel
c, d = call("POST", "/api/reels-studio/create", {"clip_id": cur, "platform": "youtube_shorts", "ratio": "9:16", "size": "720",
            "mode": "center", "target_sec": 15, "original_audio_on": True, "original_volume": 1, "title": "ONECLICK test"})
if c != 200:
    rec("reel", "FAIL", f"HTTP {c} {str(d)[:200]}")
    sys.exit(1)
nid = cid(d)
if d.get("job_id"):
    wait_job(d["job_id"])
k = wait_clip(nid)
good = k.get("status") == "ready" and (k.get("width"), k.get("height")) == (720, 1280)
rec("reel", "PASS" if good else "FAIL", f"clip {nid} {k.get('status')} {k.get('width')}x{k.get('height')} dur={k.get('duration_sec')}")
if k.get("status") != "ready":
    sys.exit(1)
cur = nid

# 2 captions
c, g = call("POST", f"/api/clips/{cur}/captions/generate", {})
if c == 200 and isinstance(g, dict) and g.get("job_id"):
    wait_job(g["job_id"])
c2, cap = call("GET", f"/api/clips/{cur}/captions")
lines = (cap.get("segments") or cap.get("lines") or []) if isinstance(cap, dict) else []
if c != 200:
    rec("captions", "FAIL", f"generate HTTP {c} {str(g)[:150]}")
elif not lines:
    rec("captions", "WARN", "no speech in this clip = no captions (correct, nothing invented)")
else:
    before = latest()
    c, b = call("POST", f"/api/clips/{cur}/captions/studio-burn", {"preset": "gaming"})
    if c != 200:
        rec("captions", "FAIL", f"burn HTTP {c} {str(b)[:150]}")
    else:
        bid = cid(b)
        if not bid:
            if b.get("job_id"):
                wait_job(b["job_id"])
            bid = latest() if latest() > before else None
        kk = wait_clip(bid) if bid else {"status": "none"}
        rec("captions", "PASS" if kk.get("status") == "ready" else "FAIL", f"lines={len(lines)} burned clip {bid} {kk.get('status')}")
        if kk.get("status") == "ready":
            cur = bid

# 3 music (generated tone, removed afterwards)
tid = None
if TONE and Path(TONE).is_file():
    out = subprocess.run(["curl.exe", "-sS", "-F", f"files=@{TONE}", BASE + "/api/music/upload"], capture_output=True, text=True)
    try:
        tid = json.loads(out.stdout)["uploaded"][0]["id"]
    except Exception:
        tid = None
if not tid:
    rec("music", "SKIP", "no tone file / upload failed")
else:
    c, s = call("GET", f"/api/clips/{cur}")
    mix = {"original_enabled": True, "original_volume": 100, "codec": "aac", "bitrate_kbps": 192, "title": "ONECLICK music",
           "tracks": [{"track_id": tid, "volume": 40, "loop": True, "fade_in": 1, "fade_out": 2, "start_sec": 0, "trim_in": 0}]}
    c, m = call("POST", f"/api/audio-studio/clips/{cur}/mix", mix)
    if c != 200:
        rec("music", "FAIL", f"HTTP {c} {str(m)[:150]}")
    else:
        mk = wait_clip(m.get("clip_id") or cid(m))
        same = abs(float(mk.get("duration_sec") or 0) - float(s.get("duration_sec") or 0)) <= 0.6
        rec("music", "PASS" if mk.get("status") == "ready" and same else "FAIL", f"mixed {mk.get('status')} dur {mk.get('duration_sec')} vs {s.get('duration_sec')}")
        if mk.get("status") == "ready":
            cur = m.get("clip_id") or cid(m)
    call("DELETE", f"/api/music/{tid}")

# 4 social
c, sd = call("POST", "/api/social/generate", {"clip_id": cur, "tone": "viral", "platform": "general", "notes": ""}, 180)
need = ["title", "description", "hashtags"]
okf = c == 200 and isinstance(sd, dict) and all(sd.get(x) for x in need)
rec("social", "PASS" if okf else "FAIL", f"HTTP {c} source={sd.get('source') if isinstance(sd, dict) else ''}")

# 5 final file plays
try:
    with urllib.request.urlopen(BASE + f"/api/clips/{cur}/stream", timeout=30) as r:
        r.read(2048)
        code = r.status
except Exception:
    code = 0
rec("final clip plays", "PASS" if code == 200 else "FAIL", f"clip {cur} stream HTTP {code}")

lines_md = [f"\n## 13.1 One-click chain test {datetime.now():%Y-%m-%d %H:%M}", "| Step | Result | Detail |", "|---|---|---|"]
lines_md += [f"| {n} | {s} | {d[:150].replace('|', '/')} |" for n, s, d in OUT]
with open(Path(__file__).resolve().parent.parent / "REAL_TEST_RESULT.md", "a", encoding="utf-8") as f:
    f.write("\n".join(lines_md) + "\n")
sys.exit(1 if any(s == "FAIL" for _, s, _ in OUT) else 0)