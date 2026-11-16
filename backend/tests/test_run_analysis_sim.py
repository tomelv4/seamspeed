# Integration test of server._run_analysis with synthetic pose + mocked Gemini (no network, no DB writes).
# Covers: measured events anchor BFC/FFC/release steps, 27 canonical steps, events dict, pose_data None fallback.
import asyncio
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402
import biomech  # noqa: E402
from test_biomech_unit import synth_pose  # noqa: E402

KEYS = [s[0] for s in biomech.STEPS]


def fake_ai(times):
    return json.dumps({"is_bowling_video": True, "overall_score": 6, "summary": "x", "action_type": "semi-open",
                       "phases": [], "faults": [], "strengths": [], "tips": [],
                       "steps": [{"key": k, "t": times.get(k), "score": 6, "status": "ok", "observation": "o", "cue": "c"} for k in KEYS],
                       "injury_risk": {"level": "low", "areas": []}})


class FakeColl:
    def __init__(self):
        self.calls = []

    async def update_one(self, q, u, **kw):
        self.calls.append(u)

    async def insert_one(self, doc):
        self.calls.append(doc)


class FakeDB:
    analyses, poses = FakeColl(), FakeColl()


def run(monkeypatch, pose_fn, ai_times, duration=2.5):
    prompts = []

    class Chat:
        def __init__(self, **kw):
            pass

        def with_model(self, *a):
            return self

        async def send_message(self, msg):
            prompts.append(msg.text)
            return fake_ai(ai_times)

    db = FakeDB()
    db.analyses, db.poses = FakeColl(), FakeColl()
    monkeypatch.setattr(server, "LlmChat", Chat)
    monkeypatch.setattr(server, "db", db)
    monkeypatch.setattr(server, "put_object", lambda *a: None)
    monkeypatch.setattr(server, "cache_path", lambda p: tempfile.mktemp())
    monkeypatch.setattr(server.pose_lib, "video_meta", lambda p: {"fps": 30, "duration": duration})
    monkeypatch.setattr(server.pose_lib, "extract_pose", pose_fn)

    async def wl(*a):
        return {"status": "low", "headline": "h", "advice": "a"}

    monkeypatch.setattr(server, "workload_summary", wl)
    path = tempfile.mktemp(suffix=".mp4")
    open(path, "wb").write(b"0")
    prof = server.Profile(device_id="TEST_sim", updated_at="")
    asyncio.run(server._run_analysis("6afb2561b38dd0e27467a2c6", path, b"0", "video/mp4", ".mp4", "", "TEST_sim", prof))
    update = db.analyses.calls[-1]["$set"]
    return update, prompts[0]


def test_measured_events_anchor_steps(monkeypatch):
    # AI gives drifting timestamps; measured events must win
    ai = {k: 0.1 + i * 0.07 for i, k in enumerate(KEYS)}
    upd, prompt = run(monkeypatch, lambda p: synth_pose("right"), ai)
    steps = upd["steps"]
    assert [s["key"] for s in steps] == KEYS
    ev = upd["events"]
    print("events", ev)
    assert ev["measured"] == ["bfc", "ffc", "release", "take_off"]
    by = {s["key"]: s for s in steps}
    assert by["bfc"]["t"] == ev["bfc"] and by["ffc"]["t"] == ev["ffc"] and by["finger_roll_release"]["t"] == ev["release"]
    ts = [s["t"] for s in steps]
    assert ts == sorted(ts)
    assert all(s["ideal"] and s["description"] for s in steps)
    assert "stride_pct_height" in by["ffc"]["metrics"] and "release_height_pct" in by["finger_roll_release"]["metrics"]
    assert "Detected events" in prompt and "BFC=1.10" in prompt
    assert upd["has_pose"] is True
    print({s["key"]: s["t"] for s in steps})


def test_pose_none_falls_back_to_ai_times(monkeypatch):
    def boom(p):
        raise RuntimeError("pose failed")

    ai = {"take_off": 1.3, "bfc": 1.6, "ffc": 1.85, "finger_roll_release": 2.0, "wrist_snap": 2.0}
    upd, prompt = run(monkeypatch, boom, ai, duration=3.0)
    assert upd["status"] == "done" and upd["has_pose"] is False
    ev = upd["events"]
    assert ev["measured"] == [] and ev["release"] == 2.0 and ev["bfc"] == 1.6
    by = {s["key"]: s for s in upd["steps"]}
    assert by["ffc"]["t"] == 1.85
    assert "MEASURED SKELETON" not in prompt


def test_no_pose_no_ai_times(monkeypatch):
    upd, _ = run(monkeypatch, lambda p: None, {})
    assert upd["status"] == "done" and all(s["t"] is None for s in upd["steps"])
