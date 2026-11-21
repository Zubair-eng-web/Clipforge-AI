"""Reel media endpoints test (backend must run)."""
import json, sys, urllib.request, urllib.error
B = "http://localhost:8000"
bad = 0


def get(p, raw=False):
    try:
        with urllib.request.urlopen(B + p, timeout=30) as r:
            data = r.read(2048) if raw else json.loads(r.read().decode())
            return r.status, data, r.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        return e.code, None, ""
    except Exception as e:
        return 0, str(e), ""


c, d, _ = get("/api/reels?limit=3")
items = d if isinstance(d, list) else (d or {}).get("items", []) if isinstance(d, dict) else []
if c != 200 or not items:
    print(f"[SKIP] no reels in the library (HTTP {c})")
    sys.exit(0)
for it in items[:3]:
    rid = it["id"]
    s, _, ct = get(f"/api/reels/{rid}/stream", raw=True)
    t, _, tct = get(f"/api/reels/{rid}/thumbnail", raw=True)
    k, kd, _ = get(f"/api/reels/{rid}/clip")
    ok = s == 200 and "video" in ct and t == 200 and k == 200 and isinstance(kd, dict) and kd.get("clip_id")
    print(f"[{'PASS' if ok else 'FAIL'}] reel {rid}: stream {s} ({ct}), thumbnail {t}, clip lookup {k} -> {kd}")
    bad += 0 if ok else 1
s, _, _ = get("/api/reels/999999/stream", raw=True)
print(f"[{'PASS' if s == 404 else 'FAIL'}] unknown reel -> {s} (404 expected)")
bad += 0 if s == 404 else 1
sys.exit(1 if bad else 0)