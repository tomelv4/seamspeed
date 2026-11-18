"""Backend tests for PaceSensei (fast-bowling analysis) API.

Covers profile, analyses CRUD, drills, progress, and coach chat (SSE).
"""
import os
import re
import subprocess
import time
import uuid

import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
DEVICE_ID = f"TEST_{uuid.uuid4()}"
HEADERS = {"X-Device-Id": DEVICE_ID}

VIDEO_PATH = "/tmp/test.mp4"


@pytest.fixture(scope="session", autouse=True)
def ensure_video():
    """Generate a tiny color-bars mp4 for analysis endpoint."""
    if os.path.exists(VIDEO_PATH) and os.path.getsize(VIDEO_PATH) > 0:
        return
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
         "-pix_fmt", "yuv420p", VIDEO_PATH],
        check=True, capture_output=True,
    )


@pytest.fixture(scope="session")
def created_analysis_ids():
    ids = []
    yield ids
    for aid in ids:
        try:
            requests.delete(f"{BASE_URL}/api/analyses/{aid}", headers=HEADERS, timeout=10)
        except Exception:
            pass
    try:
        requests.delete(f"{BASE_URL}/api/coach/messages", headers=HEADERS, timeout=10)
    except Exception:
        pass


# ---------------------------------------------------------------- health / root
def test_root():
    r = requests.get(f"{BASE_URL}/api/", timeout=15)
    assert r.status_code == 200
    assert "PACED" in r.json().get("message", "")


# ---------------------------------------------------------------- profile
def test_profile_default():
    r = requests.get(f"{BASE_URL}/api/profile", headers=HEADERS, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["device_id"] == DEVICE_ID
    assert data["name"] == "Bowler"
    assert data["bowling_arm"] in ("Right", "Left")


def test_profile_missing_header():
    r = requests.get(f"{BASE_URL}/api/profile", timeout=15)
    assert r.status_code == 422


def test_profile_update_and_persist():
    body = {"name": "TEST_Jofra", "bowling_arm": "Right", "bowling_style": "Fast", "level": "Pro"}
    r = requests.put(f"{BASE_URL}/api/profile", json=body, headers=HEADERS, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["name"] == "TEST_Jofra"
    assert data["level"] == "Pro"
    # GET back
    r2 = requests.get(f"{BASE_URL}/api/profile", headers=HEADERS, timeout=15)
    assert r2.json()["name"] == "TEST_Jofra"


# ---------------------------------------------------------------- drills
def test_drills_list():
    r = requests.get(f"{BASE_URL}/api/drills", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    drills = r.json()
    assert isinstance(drills, list) and len(drills) >= 12
    assert all("recommended" in d for d in drills)


def test_drills_filter_phase():
    r = requests.get(f"{BASE_URL}/api/drills", params={"phase": "release"},
                     headers=HEADERS, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert all(d["phase"] == "release" for d in data)


def test_drill_detail():
    r = requests.get(f"{BASE_URL}/api/drills/d1", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    assert r.json()["id"] == "d1"


def test_drill_detail_not_found():
    r = requests.get(f"{BASE_URL}/api/drills/missing", headers=HEADERS, timeout=15)
    assert r.status_code == 404


# ---------------------------------------------------------------- analyses
def test_list_analyses_empty():
    r = requests.get(f"{BASE_URL}/api/analyses", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_analysis_invalid_id():
    r = requests.get(f"{BASE_URL}/api/analyses/not-an-objectid", headers=HEADERS, timeout=15)
    assert r.status_code == 404


def test_delete_analysis_invalid_id():
    r = requests.delete(f"{BASE_URL}/api/analyses/not-an-objectid", headers=HEADERS, timeout=15)
    assert r.status_code == 404


def test_create_analysis_and_get(created_analysis_ids):
    """Heavy: ~5-60s Gemini call. Uploads a dummy clip."""
    with open(VIDEO_PATH, "rb") as f:
        files = {"video": ("test.mp4", f, "video/mp4")}
        data = {"notes": "TEST_check"}
        r = requests.post(f"{BASE_URL}/api/analyses", files=files, data=data,
                          headers=HEADERS, timeout=180)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["device_id"] == DEVICE_ID
    assert "is_bowling_video" in body
    # color bars should not be classified as a bowling video
    assert body["is_bowling_video"] is False
    assert "id" in body and body["id"]
    created_analysis_ids.append(body["id"])
    # GET persisted
    g = requests.get(f"{BASE_URL}/api/analyses/{body['id']}", headers=HEADERS, timeout=15)
    assert g.status_code == 200
    assert g.json()["id"] == body["id"]


# ---------------------------------------------------------------- progress
def test_progress_shape():
    r = requests.get(f"{BASE_URL}/api/progress", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    data = r.json()
    for k in ("points", "phase_avg", "top_faults", "best_score", "best_pace", "total", "step_trends"):
        assert k in data
    assert isinstance(data["step_trends"], list)


# ---------------------------------------------------------------- AI Coach practice tracking
def test_coach_drill_history_starts_empty():
    r = requests.get(f"{BASE_URL}/api/coach/drills/history", headers=HEADERS, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total_completions"] == 0
    assert data["focuses"] == []
    assert data["sessions"] == []


def test_coach_drill_completion_requires_owned_prescribed_drill():
    r = requests.post(
        f"{BASE_URL}/api/coach/drills/not-an-objectid/front_knee_bracing/complete",
        headers=HEADERS, json={}, timeout=15,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------- coach chat
def test_coach_chat_sse_streaming():
    r = requests.post(f"{BASE_URL}/api/coach/chat", headers=HEADERS,
                      json={"message": "Give me one tip in 1 short sentence."},
                      stream=True, timeout=120)
    assert r.status_code == 200, r.text
    ct = r.headers.get("content-type", "")
    assert "text/event-stream" in ct, ct
    deltas = []
    done = False
    t0 = time.time()
    for raw in r.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        if raw.startswith("data: "):
            payload = raw[6:]
            if payload == "[DONE]":
                done = True
                break
            import json as _json
            try:
                evt = _json.loads(payload)
            except Exception:
                continue
            if "delta" in evt:
                deltas.append(evt["delta"])
            elif "error" in evt:
                pytest.fail(f"SSE error from coach: {evt['error']}")
        if time.time() - t0 > 110:
            break
    assert done, "SSE stream did not emit [DONE]"
    assert deltas, "No text deltas received"
    assert len("".join(deltas).strip()) > 0


def test_coach_chat_empty_message():
    r = requests.post(f"{BASE_URL}/api/coach/chat", headers=HEADERS,
                      json={"message": "   "}, timeout=30)
    assert r.status_code == 400


def test_coach_messages_persisted_and_clear():
    r = requests.get(f"{BASE_URL}/api/coach/messages", headers=HEADERS, timeout=15)
    assert r.status_code == 200
    msgs = r.json()
    assert isinstance(msgs, list)
    # After previous streaming test we should have at least one user + assistant pair
    roles = {m["role"] for m in msgs}
    assert "user" in roles
    # Clear
    d = requests.delete(f"{BASE_URL}/api/coach/messages", headers=HEADERS, timeout=15)
    assert d.status_code == 200
    r2 = requests.get(f"{BASE_URL}/api/coach/messages", headers=HEADERS, timeout=15)
    assert r2.json() == []
