"""10.4 remaining cases: fixed 60 s, fixed 180 s, custom category, duplicate guard. Backend must run."""
import json, sys, time, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
BASE = "http://localhost:8000"
VID = int(sys.argv[1]) if len(sys.argv) > 1 else 1
OUT = []

def call(m, p, b=None, t=60):
    data = json.dumps(b).encode() if b is not None else None
    req = urllib.request.Request(BASE + p, data=data, method=m, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}

def wait(job, limit=1800):
    t0 = time.time()
    while time.time() - t0 < limit:
        c, j = call("GET", f"/api/jobs/{job}")
        if j.get("status") in ("completed", "failed", "cancelled"):
            return j
        time.sleep(3)
    return {"status": "timeout"}

def run(cats, conf=40):
    body = {"categories": cats, "options": {"confidence": conf, "min_scene_sec": 5, "use_vision": True, "auto_extract": False}}
    c, d = call("POST", f"/api/scene-ai/videos/{VID}/run", body)
    if c != 200:
        return None, f"HTTP {c} {str(d)[:150]}"
    j = wait(d["job_id"])
    return (j["status"] == "completed"), (j.get("error") or j["status"])

def scenes(cat):
    c, d = call("GET", f"/api/scene-ai/videos/{VID}/scenes?category={cat}")
    return d.get("items", []) if c == 200 else []

def rec(name, st, detail):
    OUT.append((name, st, detail))
    print(f"[{st}] {name} - {detail}")

def fixed(name, secs):
    ok, err = run([{"key": "fighting", "duration": secs}])
    if not ok:
        return rec(name, "FAIL", f"job: {err}")
    it = scenes("fighting")
    if not it:
        return rec(name, "WARN", "no fighting scene found (try another category)")
    bad = [s["id"] for s in it if s["duration_sec"] > secs + 0.6]
    durs = sorted(round(s["duration_sec"]) for s in it)
    rec(name, "FAIL" if bad else "PASS", f"scenes={len(it)} durations={durs} too_long={bad}")

def clear(cat):
    for x in scenes(cat):
        call("DELETE", f"/api/scene-ai/scenes/{x['id']}")

clear("fighting")
fixed("10.4 fixed 60 s", 60)
clear("fighting")
fixed("10.4 fixed 180 s", 180)

ok, err = run([{"key": "custom", "custom_text": "helicopter landing", "duration": "auto"}])
if ok:
    rec("10.4 custom category", "PASS", f"job completed, scenes={len(scenes('custom'))} (0 is fine if there is no helicopter)")
else:
    rec("10.4 custom category", "FAIL", f"job: {err}")

it = scenes("fighting")
if not it:
    rec("10.4 duplicate guard", "SKIP", "no fighting scene to extract")
else:
    s0 = sorted(it, key=lambda s: s["status"] != "detected")[0]
    c, e = call("POST", f"/api/scene-ai/videos/{VID}/extract", {"scene_ids": [s0["id"]], "mode": "accurate", "subtitles": False})
    st = None
    for _ in range(200):
        row = next((x for x in scenes("fighting") if x["id"] == s0["id"]), None)
        st = row.get("clip_status") if row else None
        if st in ("ready", "failed", "cancelled"):
            break
        time.sleep(3)
    if st != "ready":
        rec("10.4 duplicate guard", "FAIL", f"extract status {st}")
    else:
        ok, err = run([{"key": "fighting", "duration": 180}])
        a0, a1 = s0["start_sec"], s0["end_sec"]
        n = 0
        for x in scenes("fighting"):
            ov = min(a1, x["end_sec"]) - max(a0, x["start_sec"])
            if ov > 0 and ov / max(min(a1 - a0, x["end_sec"] - x["start_sec"]), 0.01) >= 0.5:
                n += 1
        rec("10.4 duplicate guard", "PASS" if (ok and n <= 1) else "FAIL", f"rerun ok={ok}, scenes overlapping the extracted one (50%+) = {n} (must be 1)")

lines = [f"\n## 10.4 remaining cases {datetime.now():%Y-%m-%d %H:%M} (video {VID})", "| Case | Result | Detail |", "|---|---|---|"]
lines += [f"| {n} | {s} | {d[:160].replace('|', '/')} |" for n, s, d in OUT]
with open(Path(__file__).resolve().parent.parent / "REAL_TEST_RESULT.md", "a", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("saved to REAL_TEST_RESULT.md")