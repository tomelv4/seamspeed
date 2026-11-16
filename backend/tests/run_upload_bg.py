# Helper: upload /tmp/person.mp4 and poll until done; dumps final JSON to /tmp/analysis_result.json
import json
import os
import sys
import time

import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
DEV = os.environ.get("DEV_ID", "TEST_iter6_bg")
out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/analysis_result.json"

aid = os.environ.get("AID")
if not aid:
    with open("/tmp/person.mp4", "rb") as f:
        r = requests.post(f"{BASE_URL}/api/analyses", headers={"X-Device-Id": DEV},
                          files={"video": ("person.mp4", f, "video/mp4")}, timeout=120)
    print("POST", r.status_code, r.text[:300], flush=True)
    aid = r.json().get("id")
t0 = time.time()
while time.time() - t0 < 420:
    g = requests.get(f"{BASE_URL}/api/analyses/{aid}", headers={"X-Device-Id": DEV}, timeout=60)
    d = g.json() if g.status_code == 200 else {}
    st = d.get("status")
    print(int(time.time() - t0), g.status_code, st, flush=True)
    if st in ("done", "failed", "error"):
        break
    time.sleep(10)
json.dump(d, open(out, "w"), indent=1)
print("WROTE", out, aid, flush=True)
