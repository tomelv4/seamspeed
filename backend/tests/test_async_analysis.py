# Async analysis pipeline tests (502 fix): POST returns fast, GET polls processing -> done, list filtering
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
DEVICE = f"TEST_async_{uuid.uuid4().hex[:8]}"
H = {"X-Device-Id": DEVICE}
STATE = {}


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for aid in STATE.get("ids", []):
        requests.delete(f"{BASE_URL}/api/analyses/{aid}", headers=H, timeout=30)


# Upload returns quickly with id + processing
def test_post_returns_fast():
    t0 = time.time()
    with open("/tmp/person.mp4", "rb") as f:
        r = requests.post(f"{BASE_URL}/api/analyses", headers=H,
                          files={"video": ("person.mp4", f, "video/mp4")}, data={"notes": "TEST_async"}, timeout=60)
    dt = time.time() - t0
    print(f"POST took {dt:.2f}s status={r.status_code} body={r.text[:200]}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "processing"
    assert isinstance(body["id"], str) and len(body["id"]) == 24
    assert dt < 5
    STATE["id"] = body["id"]
    STATE.setdefault("ids", []).append(body["id"])


# Processing doc is retrievable and excluded from list
def test_processing_state_and_list_excludes():
    aid = STATE.get("id") or pytest.skip("no id")
    g = requests.get(f"{BASE_URL}/api/analyses/{aid}", headers=H, timeout=30)
    assert g.status_code == 200
    assert g.json()["status"] == "processing"
    lst = requests.get(f"{BASE_URL}/api/analyses", headers=H, timeout=30).json()
    assert aid not in [a["id"] for a in lst]


# Other device cannot read the doc
def test_other_device_404():
    aid = STATE.get("id") or pytest.skip("no id")
    g = requests.get(f"{BASE_URL}/api/analyses/{aid}", headers={"X-Device-Id": "TEST_other"}, timeout=30)
    assert g.status_code == 404


# Poll until done (up to 5 min)
def test_poll_until_done():
    aid = STATE.get("id") or pytest.skip("no id")
    t0 = time.time()
    data = None
    while time.time() - t0 < 330:
        g = requests.get(f"{BASE_URL}/api/analyses/{aid}", headers=H, timeout=30)
        assert g.status_code == 200, g.text
        data = g.json()
        if data.get("status") != "processing":
            break
        time.sleep(5)
    print(f"Finished in {time.time() - t0:.0f}s status={data.get('status')} error={data.get('error')}")
    assert data["status"] == "done", data.get("error")
    assert len(data["steps"]) == 27
    assert isinstance(data["phases"], list) and data["phases"]
    assert isinstance(data["injury_risk"], dict)
    assert any(a.get("key") == "workload" for a in data["injury_risk"].get("areas", []))
    assert data["video_path"]
    assert isinstance(data["has_pose"], bool)
    print(f"has_pose={data['has_pose']} is_bowling={data['is_bowling_video']} score={data['overall_score']}")
    STATE["done"] = data


# Done doc now appears in list
def test_list_includes_done():
    if "done" not in STATE:
        pytest.skip("not done")
    lst = requests.get(f"{BASE_URL}/api/analyses", headers=H, timeout=30).json()
    assert STATE["id"] in [a["id"] for a in lst]


# Pose endpoint works when has_pose
def test_pose_endpoint():
    d = STATE.get("done") or pytest.skip("not done")
    if not d["has_pose"]:
        pytest.skip("no pose")
    r = requests.get(f"{BASE_URL}/api/analyses/{STATE['id']}/pose", headers=H, timeout=30)
    assert r.status_code == 200
    assert r.json()["frames"]


# Invalid upload: missing file -> 422
def test_missing_video_422():
    r = requests.post(f"{BASE_URL}/api/analyses", headers=H, data={"notes": "x"}, timeout=30)
    assert r.status_code == 422
