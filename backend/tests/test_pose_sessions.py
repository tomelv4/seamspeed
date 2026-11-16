"""Iteration 2: 27-step analysis w/ pose, pose & media endpoints, TTS, live coaching sessions."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/")
DEVICE_ID = f"TEST_{uuid.uuid4().hex[:12]}"
OTHER = f"TEST_{uuid.uuid4().hex[:12]}"
H = {"X-Device-Id": DEVICE_ID}
H_OTHER = {"X-Device-Id": OTHER}
VIDEO = "/tmp/person.mp4"
STEP_FIELDS = {"key", "name", "phase", "t", "score", "status", "observation", "cue", "metrics"}

state = {}


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    for aid in state.get("analyses", []):
        requests.delete(f"{BASE_URL}/api/analyses/{aid}", headers=H, timeout=30)


# --- Analysis with 27 steps + pose
class TestAnalysisPose:
    def test_create_analysis_steps(self):
        with open(VIDEO, "rb") as f:
            r = requests.post(f"{BASE_URL}/api/analyses", headers=H,
                              files={"video": ("person.mp4", f, "video/mp4")}, data={"notes": "TEST_"}, timeout=180)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        state.setdefault("analyses", []).append(d["id"])
        state["analysis"] = d
        assert "_id" not in d
        assert len(d["steps"]) == 27
        for s in d["steps"]:
            assert STEP_FIELDS <= set(s.keys()), s.keys()
        assert d["video_path"]
        assert isinstance(d["video_meta"], dict) and d["video_meta"].get("width", 0) > 0
        assert d["has_pose"] is True
        print("is_bowling:", d.get("is_bowling_video"), "meta:", d["video_meta"])
        print("metrics sample:", [s["metrics"] for s in d["steps"] if s["metrics"]][:2])

    def test_steps_persisted(self):
        aid = state["analysis"]["id"]
        r = requests.get(f"{BASE_URL}/api/analyses/{aid}", headers=H, timeout=30)
        assert r.status_code == 200
        assert len(r.json()["steps"]) == 27

    def test_pose_owner(self):
        aid = state["analysis"]["id"]
        r = requests.get(f"{BASE_URL}/api/analyses/{aid}/pose", headers=H, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["width"] > 0 and d["height"] > 0
        assert len(d["frames"]) > 0
        f0 = d["frames"][0]
        assert "t" in f0 and "k" in f0
        assert "_id" not in d and "device_id" not in d

    def test_pose_other_device_404(self):
        aid = state["analysis"]["id"]
        r = requests.get(f"{BASE_URL}/api/analyses/{aid}/pose", headers=H_OTHER, timeout=30)
        assert r.status_code == 404

    def test_media_owner(self):
        aid = state["analysis"]["id"]
        r = requests.get(f"{BASE_URL}/api/media/{aid}", params={"d": DEVICE_ID}, timeout=60)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("video/mp4")
        assert len(r.content) > 1000

    def test_media_range_request(self):
        aid = state["analysis"]["id"]
        r = requests.get(f"{BASE_URL}/api/media/{aid}", params={"d": DEVICE_ID},
                         headers={"Range": "bytes=0-99"}, timeout=60)
        print("range status:", r.status_code, r.headers.get("content-range"))
        assert r.status_code in (200, 206)

    def test_media_wrong_device_404(self):
        aid = state["analysis"]["id"]
        r = requests.get(f"{BASE_URL}/api/media/{aid}", params={"d": OTHER}, timeout=30)
        assert r.status_code == 404


# --- Live coaching sessions + TTS
class TestSessions:
    def test_start_session(self):
        r = requests.post(f"{BASE_URL}/api/sessions", headers=H, json={"focus": "Pace"}, timeout=150)
        assert r.status_code == 200, r.text[:500]
        d = r.json()
        state["session"] = d
        assert d["status"] == "active" and d["focus"] == "Pace"
        assert len(d["intro"]) > 10
        assert len(d["intro_audio"]) == 40
        print("intro:", d["intro"])

    def test_tts_audio(self):
        key = state["session"]["intro_audio"]
        r = requests.get(f"{BASE_URL}/api/tts/{key}.mp3", timeout=60)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("audio/mpeg")
        assert len(r.content) > 1000

    def test_tts_bad_key_404(self):
        r = requests.get(f"{BASE_URL}/api/tts/{'0' * 40}.mp3", timeout=30)
        assert r.status_code == 404

    def test_ball(self):
        sid = state["session"]["id"]
        with open(VIDEO, "rb") as f:
            r = requests.post(f"{BASE_URL}/api/sessions/{sid}/balls", headers=H,
                              files={"video": ("ball.mp4", f, "video/mp4")}, timeout=180)
        assert r.status_code == 200, r.text[:500]
        b = r.json()
        assert b["n"] == 1
        assert b["feedback"] and b["next_target"]
        assert len(b["audio"]) == 40
        assert isinstance(b["score"], float)
        assert "NEXT:" not in b["feedback"]
        print("ball:", b)

    def test_session_other_device_404(self):
        sid = state["session"]["id"]
        r = requests.get(f"{BASE_URL}/api/sessions/{sid}", headers=H_OTHER, timeout=30)
        assert r.status_code == 404

    def test_end_session(self):
        sid = state["session"]["id"]
        r = requests.post(f"{BASE_URL}/api/sessions/{sid}/end", headers=H, timeout=150)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ended"
        assert len(d["summary"]) > 10
        assert len(d["balls"]) == 1
        print("summary:", d["summary"])

    def test_list_sessions(self):
        r = requests.get(f"{BASE_URL}/api/sessions", headers=H, timeout=30)
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()]
        assert state["session"]["id"] in ids

    def test_ball_after_end_400(self):
        sid = state["session"]["id"]
        with open(VIDEO, "rb") as f:
            r = requests.post(f"{BASE_URL}/api/sessions/{sid}/balls", headers=H,
                              files={"video": ("ball.mp4", f, "video/mp4")}, timeout=60)
        assert r.status_code == 400

    def test_invalid_session_404(self):
        r = requests.get(f"{BASE_URL}/api/sessions/notanid", headers=H, timeout=30)
        assert r.status_code == 404
