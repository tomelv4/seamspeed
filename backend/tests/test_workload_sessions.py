# Iteration 4: workload tracker, profile age_band, injury scanner areas, full coaching sessions
import os
import uuid
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL").rstrip("/")
VIDEO = "/tmp/person.mp4"


def dev():
    return f"TEST_wl_{uuid.uuid4().hex[:8]}"


def h(d):
    return {"X-Device-Id": d}


def iso(n):
    return (date.today() - timedelta(days=n)).isoformat()


def log(d, n, balls, intensity=7):
    r = requests.post(f"{BASE_URL}/api/workload", json={"date": iso(n), "balls": balls, "intensity": intensity}, headers=h(d), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def cleanup(d):
    r = requests.get(f"{BASE_URL}/api/workload", headers=h(d), timeout=30)
    for e in r.json().get("entries", []):
        requests.delete(f"{BASE_URL}/api/workload/{e['id']}", headers=h(d), timeout=30)


# --- Workload GET shape
class TestWorkload:
    def test_empty_shape(self):
        d = dev()
        r = requests.get(f"{BASE_URL}/api/workload", headers=h(d), timeout=30)
        assert r.status_code == 200
        j = r.json()
        for k in ["acute", "previous_week", "chronic_weekly", "acwr", "rest_days_7", "streak", "weeks", "flags", "status", "headline", "advice", "entries"]:
            assert k in j, k
        assert j["acute"] == 0 and j["acwr"] is None and len(j["weeks"]) == 8 and j["status"] == "low" and j["rest_days_7"] == 7

    def test_missing_header(self):
        assert requests.get(f"{BASE_URL}/api/workload", timeout=30).status_code == 422

    def test_log_and_validation(self):
        d = dev()
        j = log(d, 0, 36, 8)
        assert j["acute"] == 36 and j["today"] == 36 and len(j["entries"]) == 1
        assert j["entries"][0]["balls"] == 36 and j["entries"][0]["intensity"] == 8 and j["entries"][0]["source"] == "manual"
        assert j["acwr"] is None  # not enough history
        bad = requests.post(f"{BASE_URL}/api/workload", json={"date": "2026-13-45", "balls": 10}, headers=h(d), timeout=30)
        assert bad.status_code == 400
        bad2 = requests.post(f"{BASE_URL}/api/workload", json={"date": iso(0), "balls": 301}, headers=h(d), timeout=30)
        assert bad2.status_code == 422
        bad3 = requests.post(f"{BASE_URL}/api/workload", json={"date": iso(0), "balls": 0}, headers=h(d), timeout=30)
        assert bad3.status_code == 422
        bad4 = requests.post(f"{BASE_URL}/api/workload", json={"date": iso(0), "balls": 10, "intensity": 11}, headers=h(d), timeout=30)
        assert bad4.status_code == 422
        cleanup(d)

    def test_delete_owner_only(self):
        d, other = dev(), dev()
        eid = log(d, 0, 12)["entries"][0]["id"]
        assert requests.delete(f"{BASE_URL}/api/workload/{eid}", headers=h(other), timeout=30).status_code == 404
        assert requests.delete(f"{BASE_URL}/api/workload/badid", headers=h(d), timeout=30).status_code == 404
        r = requests.delete(f"{BASE_URL}/api/workload/{eid}", headers=h(d), timeout=30)
        assert r.status_code == 200 and r.json() == {"ok": True}
        j = requests.get(f"{BASE_URL}/api/workload", headers=h(d), timeout=30).json()
        assert j["entries"] == [] and j["acute"] == 0

    def test_acwr_spike_high_flag(self):
        d = dev()
        for n in (25, 22, 18, 15, 11, 8):
            log(d, n, 12)
        j = log(d, 2, 150)
        assert j["acwr"] is not None and j["acwr"] > 1.5, j
        assert any(f["level"] == "high" and "ratio" in f["text"].lower() for f in j["flags"]), j["flags"]
        assert j["status"] == "high"
        cleanup(d)

    def test_streak_flag(self):
        d = dev()
        for n in (0, 1, 2, 3):
            j = log(d, n, 12)
        assert j["streak"] == 4 and j["rest_days_7"] == 3
        assert any("in a row" in f["text"] for f in j["flags"]), j["flags"]
        cleanup(d)

    def test_age_band_guide_flag(self):
        d = dev()
        r = requests.put(f"{BASE_URL}/api/profile", json={"name": "TEST_U16", "bowling_arm": "Right", "bowling_style": "Fast", "level": "Club", "age_band": "Under 16"}, headers=h(d), timeout=30)
        assert r.status_code == 200 and r.json()["age_band"] == "Under 16"
        assert requests.get(f"{BASE_URL}/api/profile", headers=h(d), timeout=30).json()["age_band"] == "Under 16"
        j = log(d, 1, 130)
        assert j["weekly_guide"] == 120
        assert any("guide" in f["text"] and f["level"] == "high" for f in j["flags"]), j["flags"]
        cleanup(d)


# --- Speak / TTS
def test_speak_and_tts():
    r = requests.post(f"{BASE_URL}/api/speak", json={"text": "Good ball, keep your head still."}, timeout=90)
    assert r.status_code == 200, r.text
    key = r.json()["audio"]
    assert key
    a = requests.get(f"{BASE_URL}/api/tts/{key}.mp3", timeout=60)
    assert a.status_code == 200 and a.headers["content-type"].startswith("audio/") and len(a.content) > 1000
    assert requests.post(f"{BASE_URL}/api/speak", json={"text": ""}, timeout=30).status_code == 422


# --- Full coaching session
class TestSession:
    def test_full_session_flow(self):
        d = dev()
        r = requests.post(f"{BASE_URL}/api/sessions", json={"focus": "Pace"}, headers=h(d), timeout=180)
        assert r.status_code == 200, r.text
        s = r.json()
        plan = s["plan"]
        assert s["intro_audio"] and s["status"] == "active"
        assert isinstance(plan["pre_session"], list) and len(plan["pre_session"]) == 4
        assert {item["name"] for item in plan["pre_session"]} >= {"Readiness check", "Review recent workload", "Hydrate and set up"}
        assert isinstance(plan["warm_up"], list) and len(plan["warm_up"]) == 5
        assert isinstance(plan["recovery"]["items"], list) and len(plan["recovery"]["items"]) == 4
        assert {item["name"] for item in plan["recovery"]["items"]} >= {"Rehydrate", "Refuel", "Restore", "Review response"}
        assert len(plan["cool_down"]) == 3
        assert 1 <= plan["bowling"]["balls"] <= 12
        assert plan["bowling"]["rest_between_deliveries"]
        assert isinstance(plan["drills"], list) and len(plan["drills"]) >= 2
        assert "balls" in plan["bowling"] and "target" in plan["bowling"]
        for k in ("name", "balls", "target"):
            assert k in plan["test"]
        assert isinstance(plan["cool_down"], list) and plan["cool_down"]
        assert isinstance(plan["tips"], list) and plan["tips"]
        sid = s["id"]
        before = requests.get(f"{BASE_URL}/api/workload", headers=h(d), timeout=30).json()["acute"]
        for block in ("bowling", "test"):
            with open(VIDEO, "rb") as f:
                b = requests.post(f"{BASE_URL}/api/sessions/{sid}/balls", files={"video": ("ball.mp4", f, "video/mp4")},
                                  data={"block": block}, headers=h(d), timeout=240)
            assert b.status_code == 200, b.text
            ball = b.json()
            assert ball["block"] == block and ball["feedback"] and ball["next_target"]
            print(block, ball["is_bowling"], ball["score"], ball["hit_target"])
        got = requests.get(f"{BASE_URL}/api/sessions/{sid}", headers=h(d), timeout=30).json()
        assert [b["block"] for b in got["balls"]] == ["bowling", "test"]
        wl = requests.get(f"{BASE_URL}/api/workload", headers=h(d), timeout=30).json()
        bowled = sum(1 for b in got["balls"] if b["is_bowling"])
        assert wl["acute"] == before + bowled
        if bowled:
            assert any(e["source"] == "session" for e in wl["entries"])
        e = requests.post(f"{BASE_URL}/api/sessions/{sid}/end", headers=h(d), timeout=180)
        assert e.status_code == 200, e.text
        ej = e.json()
        assert ej["status"] == "ended" and isinstance(ej["achievements"], list) and ej["summary"]
        print("achievements", ej["achievements"], "test_result", ej["test_result"])
        if got["balls"][1]["is_bowling"]:
            assert ej["test_result"]["balls"] == 1
        late = requests.post(f"{BASE_URL}/api/sessions/{sid}/balls", files={"video": ("b.mp4", b"x", "video/mp4")}, headers=h(d), timeout=30)
        assert late.status_code == 400
        assert requests.get(f"{BASE_URL}/api/sessions/{sid}", headers=h(dev()), timeout=30).status_code == 404
        cleanup(d)


# --- Analysis injury scanner areas
def test_analysis_injury_areas():
    d = dev()
    with open(VIDEO, "rb") as f:
        r = requests.post(f"{BASE_URL}/api/analyses", files={"video": ("person.mp4", f, "video/mp4")}, headers=h(d), timeout=300)
    assert r.status_code == 200, r.text
    a = r.json()
    print("is_bowling", a.get("is_bowling_video"), "id", a.get("id"))
    areas = a.get("injury_risk", {}).get("areas", [])
    keys = [x["key"] for x in areas]
    print("areas", keys)
    assert "workload" in keys
    if a.get("is_bowling_video"):
        for k in ("lumbar_spine", "side_strain", "front_leg", "shoulder", "hamstring_groin"):
            assert k in keys, keys
    with open("/tmp/iter4_analysis_id.txt", "w") as fh:
        fh.write(f"{d} {a.get('id')} {a.get('is_bowling_video')}")
