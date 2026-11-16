# Helper: create an analysis for a given browser device id (used by UI tests)
import os
import sys
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
dev = sys.argv[1]
with open("/tmp/test.mp4", "rb") as f:
    r = requests.post(
        f"{BASE_URL}/api/analyses",
        headers={"X-Device-Id": dev},
        files={"video": ("test.mp4", f, "video/mp4")},
        data={"notes": "TEST_ui_analysis"},
        timeout=240,
    )
print(r.status_code)
print(r.text[:800])
