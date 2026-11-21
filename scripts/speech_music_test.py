import json, subprocess, sys, time, urllib.request, urllib.error

BASE = "http://localhost:8000"
video, music = sys.argv[1], sys.argv[2]

def call(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, path, e.read().decode()[:300]); return None

def find_id(d):
    if not isinstance(d, dict): return None
    for k in ("id", "video_id"):
        if isinstance(d.get(k), int): return d[k]
    for k in ("video", "item", "data"):
        if isinstance(d.get(k), dict):
            r = find_id(d[k])
            if r is not None: return r
    return None

# 1) upload field name from openapi
spec = call("GET", "/openapi.json") or {"paths": {}, "components": {"schemas": {}}}
field = "file"
try:
    body = spec["paths"]["/api/videos/upload"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]
    if "$ref" in body:
        body = spec["components"]["schemas"][body["$ref"].split("/")[-1]]
    print("Upload form fields:", list(body.get("properties", {}).keys()))
    for name, p in body.get("properties", {}).items():
        if p.get("format") == "binary" or (p.get("items") or {}).get("format") == "binary":
            field = name; break
except Exception as e:
    print("openapi read problem:", e)
try:
    props = list(body.get("properties", {}).keys())
    if field == "file" and len(props) == 1: field = props[0]  # only_one_field_fix
except Exception:
    pass
print("Using field:", field)

# 2) upload (raw response is printed)
r = subprocess.run(["curl.exe", "-s", "-w", "\nHTTP_CODE=%{http_code}", "-F", field + "=@" + video, BASE + "/api/videos/upload"],
                   capture_output=True, text=True)
print("RAW upload response:", r.stdout[:600], r.stderr[:200])
raw = r.stdout.rsplit("\nHTTP_CODE=", 1)[0]
try:
    vid = find_id(json.loads(raw))
except Exception:
    vid = None

# 3) fallback: find the newest video in the library
if vid is None:
    lst = call("GET", "/api/videos") or []
    items = lst if isinstance(lst, list) else (lst.get("videos") or lst.get("items") or [])
    if items:
        vid = max(i.get("id", 0) for i in items if isinstance(i, dict))
        print("Fallback: using newest library video id", vid)
if vid is None:
    print("[FAIL] video id nahi mila"); sys.exit(1)
print("video_id =", vid)

# 4) clip 5s..65s
r = call("POST", "/api/clips", {"video_id": vid, "start_sec": 5, "end_sec": 65, "title": "SPEECHTEST", "mode": "accurate"})
if not r:
    print("[FAIL] clip nahi bani"); sys.exit(1)
cid = r.get("id") or (r.get("clip") or {}).get("id")
print("clip_id =", cid)
c = {}
for _ in range(100):
    time.sleep(3)
    c = call("GET", "/api/clips/%s" % cid) or {}
    c = c.get("clip", c)
    if c.get("status") in ("ready", "failed", "cancelled"):
        break
print("clip status =", c.get("status"))
if c.get("status") != "ready":
    print("[FAIL] clip ready nahi hui"); sys.exit(1)

print("=== ONE-CLICK CHAIN (speech + real music) ===")
sys.exit(subprocess.run([sys.executable, "scripts/test_one_click_chain.py", str(cid), music]).returncode)