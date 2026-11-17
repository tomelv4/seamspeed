import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import biomech
from analysis_contract import normalise_model_payload, parse_model_json


def valid_payload():
    return {
        "is_bowling_video": True,
        "overall_score": 7.5,
        "summary": "A balanced delivery with room to improve.",
        "action_type": "side-on",
        "camera_view": "side_on",
        "camera_view_confidence": "high",
        "release_evidence": {"ball_separation_visible": True, "confidence": "high", "notes": "Ball visibly leaves the hand."},
        "phases": [
            {"key": key, "name": name, "score": 7, "feedback": "Visible and repeatable."}
            for key, name in (
                ("run_up", "Run-up"), ("load", "Load"), ("back_foot", "BFC"),
                ("front_foot", "FFC"), ("release", "Release"), ("follow_through", "Finish"),
            )
        ],
        "steps": [
            {"key": key, "t": i * 0.1, "score": 7, "status": "good",
             "observation": "The movement is visible.", "cue": "Keep it controlled."}
            for i, (key, *_rest) in enumerate(biomech.STEPS)
        ],
        "faults": [
            {"title": "Example fault", "phase": "front_foot", "severity": "medium",
             "description": "A visible pattern.", "fix": "Use a simple cue."},
            {"title": "High priority", "phase": "back_foot", "severity": "high",
             "description": "A higher-priority visible pattern.", "fix": "Address this first."},
            {"title": "Invalid fault", "phase": "unknown", "severity": "high",
             "description": "Should be dropped.", "fix": ""},
        ],
        "strengths": ["Good rhythm", 12, ""],
        "tips": ["Repeat the action"],
    }


def test_parse_model_json_accepts_fences_and_preamble():
    result = parse_model_json('Here is the result:\n\x60\x60\x60json\n{"summary":"A {brace} inside text","ok":true}\n\x60\x60\x60')
    assert result == {"summary": "A {brace} inside text", "ok": True}


@pytest.mark.parametrize("raw", ["no json", "[1, 2]", "{broken json}", None])
def test_parse_model_json_rejects_invalid_responses(raw):
    with pytest.raises(ValueError):
        parse_model_json(raw)


def test_normalise_produces_all_27_steps_and_sanitises_faults():
    result = normalise_model_payload(valid_payload(), duration=4.0)
    assert len(result["steps"]) == 27
    assert len({step["key"] for step in result["steps"]}) == 27
    assert len(result["faults"]) == 2
    assert result["faults"][0]["title"] == "High priority"
    assert result["faults"][0]["step_key"] in {key for key, _name, phase, *_rest in biomech.STEPS if phase == "back_foot"}
    assert result["faults"][1]["step_key"] in {key for key, _name, phase, *_rest in biomech.STEPS if phase == "front_foot"}
    assert result["overall_score"] == 7.0
    assert result["overall_score_assessable"] is True
    assert result["strengths"] == ["Good rhythm"]


def test_overall_and_phase_scores_are_derived_from_step_evidence():
    payload = valid_payload()
    payload["overall_score"] = 10
    for step in payload["steps"]:
        step["score"] = 5
        if step["phase"] == "run_up":
            step["score"] = 9
    result = normalise_model_payload(payload, duration=4.0)
    run_up = next(phase for phase in result["phases"] if phase["key"] == "run_up")
    assert run_up["score"] == 9
    assert result["overall_score"] == 5.7


def test_normalise_marks_missing_and_unassessable_steps_not_visible():
    payload = valid_payload()
    payload["steps"] = [step for step in payload["steps"] if step["key"] != "finger_roll_release"]
    payload["steps"][0]["status"] = "not_visible"
    payload["steps"][0]["t"] = 0.0
    result = normalise_model_payload(payload, duration=4.0)
    first = result["steps"][0]
    release = next(step for step in result["steps"] if step["key"] == "finger_roll_release")
    assert first["status"] == "not_visible" and first["t"] is None and first["score"] == 0
    assert release["status"] == "not_visible" and release["t"] is None
    assert result["overall_score_assessable"] is True  # 25 steps remain assessable


def test_normalise_clamps_scores_and_rejects_out_of_clip_or_nonmonotonic_times():
    payload = valid_payload()
    payload["steps"][0]["score"] = 14
    payload["steps"][0]["t"] = 0.2
    payload["steps"][1]["t"] = 99
    payload["steps"][2]["t"] = 0.15
    result = normalise_model_payload(payload, duration=4.0)
    assert result["steps"][0]["score"] == 10
    assert result["steps"][1]["t"] is None
    assert result["steps"][2]["t"] is None


def test_release_step_requires_explicit_ball_separation_evidence():
    payload = valid_payload()
    payload["release_evidence"] = {"ball_separation_visible": False, "confidence": "low", "notes": "Ball is obscured."}
    result = normalise_model_payload(payload, duration=4.0)
    release = next(step for step in result["steps"] if step["key"] == "finger_roll_release")
    assert release["status"] == "not_visible"
    assert release["t"] is None
    assert result["release_evidence"]["ball_separation_visible"] is False


def test_non_bowling_video_is_not_scored_or_faulted():
    payload = valid_payload()
    payload["is_bowling_video"] = False
    result = normalise_model_payload(payload, duration=4.0)
    assert result["overall_score_assessable"] is False
    assert all(step["status"] == "not_visible" for step in result["steps"])
    assert all(phase["assessable"] is False for phase in result["phases"])
    assert result["faults"] == []


def test_normalise_missing_phase_is_explicitly_unassessable():
    payload = valid_payload()
    payload["phases"] = [p for p in payload["phases"] if p["key"] != "release"]
    release_keys = {key for key, _name, phase, *_rest in biomech.STEPS if phase == "release"}
    for step in payload["steps"]:
        if step["key"] in release_keys:
            step["status"] = "not_visible"
    payload["faults"].append({"title": "Unsupported release fault", "phase": "release", "severity": "high",
                              "description": "The phase is not assessable.", "fix": ""})
    result = normalise_model_payload(payload, duration=4.0)
    phase = next(p for p in result["phases"] if p["key"] == "release")
    assert phase["assessable"] is False
    assert phase["feedback"] == "Not enough clear visual evidence to assess this phase."
    assert all(fault["phase"] != "release" for fault in result["faults"])
