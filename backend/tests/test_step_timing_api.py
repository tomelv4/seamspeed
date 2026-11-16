# API tests for 27-step timed analysis structure. Requires ANALYSIS_ID + DEVICE_ID env of a finished analysis
# (create one with tests/run_upload_bg.py, which uploads /tmp/person.mp4 and polls until done).
import os

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
AID = os.environ.get("ANALYSIS_ID")
DEV = os.environ.get("DEVICE_ID")
EVENT_STEPS = {"bfc": "bfc", "ffc": "ffc", "finger_roll_release": "release", "take_off": "take_off"}


@pytest.fixture(scope="module")
def analysis():
    if not AID or not DEV:
        pytest.skip("ANALYSIS_ID/DEVICE_ID not set")
    r = requests.get(f"{BASE_URL}/api/analyses/{AID}", headers={"X-Device-Id": DEV}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    if d.get("status") != "done":
        pytest.skip(f"analysis status {d.get('status')}: {d.get('error')}")
    return d


def test_no_mongo_id(analysis):
    assert "_id" not in analysis and analysis["id"] == AID


def test_27_steps_canonical_order(analysis):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import biomech
    assert [s["key"] for s in analysis["steps"]] == [s[0] for s in biomech.STEPS]


def test_each_step_has_description_ideal_metrics(analysis):
    for s in analysis["steps"]:
        assert s["description"] and s["ideal"] and s["name"], s["key"]
        assert isinstance(s["metrics"], dict)
        assert s["status"] in ("good", "ok", "fault", "not_visible")


def test_times_non_decreasing(analysis):
    ts = [s["t"] for s in analysis["steps"] if s["t"] is not None]
    assert ts == sorted(ts), ts


def test_events_present_when_pose(analysis):
    if not analysis.get("has_pose"):
        pytest.skip("no pose detected")
    ev = analysis.get("events") or {}
    for k in ("take_off", "bfc", "ffc", "release", "measured"):
        assert k in ev, k
    assert ev["take_off"] < ev["bfc"] < ev["ffc"] < ev["release"], ev


def test_event_steps_match_events(analysis):
    ev = analysis.get("events") or {}
    if not ev:
        pytest.skip("no events")
    by = {s["key"]: s for s in analysis["steps"]}
    for sk, ek in EVENT_STEPS.items():
        assert by[sk]["t"] == pytest.approx(ev[ek], abs=1e-3), (sk, by[sk]["t"], ev[ek])


def test_times_within_duration(analysis):
    dur = (analysis.get("video_meta") or {}).get("duration") or 0
    if not dur:
        pytest.skip("no duration")
    assert all(s["t"] is None or 0 <= s["t"] <= dur + 0.05 for s in analysis["steps"])


def test_list_endpoint_contains_analysis():
    if not AID:
        pytest.skip("no id")
    r = requests.get(f"{BASE_URL}/api/analyses", headers={"X-Device-Id": DEV}, timeout=60)
    assert r.status_code == 200
    body = r.json()
    items = body if isinstance(body, list) else body.get("items", body.get("analyses", []))
    assert any(a.get("id") == AID for a in items)


def test_pose_endpoint(analysis):
    r = requests.get(f"{BASE_URL}/api/analyses/{AID}/pose", headers={"X-Device-Id": DEV}, timeout=60)
    assert r.status_code in (200, 404), r.status_code
