def test_recurring_fault_history_requires_exact_timestamped_fault_step():
    from analysis_contract import build_recurring_fault_history

    analyses = [
        {
            "created_at": "2026-11-01T10:00:00Z",
            "camera_view": "side_on", "camera_view_confidence": "high",
            "steps": [
                {"key": "front_knee_bracing", "name": "Front-leg bracing", "t": 2.1,
                 "status": "fault", "coaching_classification": "fault"},
                {"key": "front_arm_elevation", "name": "Front-arm position", "t": 1.8,
                 "status": "ok", "coaching_classification": "opportunity"},
                {"key": "back_leg_swing", "name": "Back-leg swing", "t": None,
                 "status": "fault", "coaching_classification": "fault"},
            ],
            "faults": [
                {"step_key": "front_knee_bracing", "title": "Front knee collapses"},
                {"step_key": "front_arm_elevation", "title": "Arm could be higher"},
                {"step_key": "back_leg_swing", "title": "Unanchored fault"},
                {"step_key": "missing_step", "title": "Unlinked fault"},
            ],
        },
        {
            "created_at": "2026-11-02T10:00:00Z",
            "camera_view": "side_on", "camera_view_confidence": "medium",
            "steps": [{"key": "front_knee_bracing", "name": "Front-leg bracing", "t": 2.2,
                       "status": "fault", "coaching_classification": "fault"}],
            "faults": [{"step_key": "front_knee_bracing", "title": "Front knee collapses"}],
        },
        {
            "created_at": "2026-11-03T10:00:00Z",
            "camera_view": "rear", "camera_view_confidence": "high",
            "steps": [{"key": "front_knee_bracing", "name": "Front-leg bracing", "t": 2.2,
                       "status": "fault", "coaching_classification": "fault"}],
            "faults": [{"step_key": "front_knee_bracing", "title": "Front knee collapses"}],
        },
        {
            "created_at": "2026-11-04T10:00:00Z",
            "camera_view": "side_on", "camera_view_confidence": "low",
            "steps": [{"key": "front_knee_bracing", "name": "Front-leg bracing", "t": 2.2,
                       "status": "fault", "coaching_classification": "fault"}],
            "faults": [{"step_key": "front_knee_bracing", "title": "Front knee collapses"}],
        },
    ]

    result = build_recurring_fault_history(analyses)
    assert len(result) == 1
    assert result[0]["step_key"] == "front_knee_bracing"
    assert result[0]["count"] == 2
    assert result[0]["last_seen"] == "2026-11-02T10:00:00Z"


import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import biomech
from analysis_contract import normalise_model_payload, parse_model_json, reconcile_synced_evidence


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
            {"title": "Example fault", "phase": "front_foot", "step_key": "front_knee_bracing", "severity": "medium",
             "description": "A visible pattern.", "fix": "Use a simple cue."},
            {"title": "High priority", "phase": "back_foot", "step_key": "bfc", "severity": "high",
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


@pytest.mark.parametrize("raw", ["no json", "[1, 2]", "[{\"summary\":\"wrong root\"}]", "{broken json}", None])
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
    phase_by_key = {key: phase for key, _name, phase, *_rest in biomech.STEPS}
    for step in payload["steps"]:
        step["score"] = 5
        if phase_by_key[step["key"]] == "run_up":
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



def test_synced_evidence_gate_removes_unanchored_step_and_recalculates_scores():
    result = normalise_model_payload(valid_payload(), duration=4.0)
    first = result["steps"][0]
    first["t"] = None

    result = reconcile_synced_evidence(result)

    assert first["status"] == "not_visible"
    assert first["score"] == 0
    assert first["evidence_level"] == "insufficient"
    assert result["overall_score_assessable"] is True
    assert result["overall_score"] == 7.0
    run_up = next(phase for phase in result["phases"] if phase["key"] == "run_up")
    assert run_up["assessable"] is True
    assert run_up["score"] == 7.0


def test_synced_evidence_gate_withholds_overall_coaching_when_coverage_is_too_low():
    result = normalise_model_payload(valid_payload(), duration=4.0)
    for step in result["steps"]:
        step["t"] = None

    result = reconcile_synced_evidence(result)

    assert result["overall_score_assessable"] is False
    assert result["overall_score"] == 0
    assert "not enough synchronized visual evidence" in result["summary"].lower()
    assert result["strengths"] == []
    assert result["tips"] == []
    assert result["faults"] == []


def test_normalise_drops_faults_without_exact_step_key():
    payload = valid_payload()
    payload["faults"].append({
        "title": "Unlinked fault", "phase": "front_foot", "severity": "high",
        "description": "No precise movement step was supplied.", "fix": "Do not guess.",
    })

    result = normalise_model_payload(payload, duration=4.0)

    assert all(fault["title"] != "Unlinked fault" for fault in result["faults"])


def test_synced_evidence_gate_requires_fault_to_match_timestamped_fault_step():
    payload = valid_payload()
    target = next(step for step in payload["steps"] if step["key"] == "front_knee_bracing")
    target["status"] = "fault"
    payload["faults"] = [
        {"title": "Supported front-knee fault", "phase": "front_foot", "step_key": "front_knee_bracing",
         "severity": "medium", "description": "Visible at the linked moment.", "fix": "Brace more firmly."},
        {"title": "Unsupported fault", "phase": "front_foot", "step_key": "front_knee_bracing",
         "severity": "high", "description": "No timestamp supports this.", "fix": "Ignore."},
    ]
    result = normalise_model_payload(payload, duration=4.0)
    result["steps"] = [dict(step) for step in result["steps"]]
    target_result = next(step for step in result["steps"] if step["key"] == "front_knee_bracing")
    target_result["t"] = None

    result = reconcile_synced_evidence(result)

    assert target_result["status"] == "not_visible"
    assert result["faults"] == []


def test_coaching_classification_separates_fault_opportunity_and_effective_variation():
    payload = valid_payload()
    by_key = {step["key"]: step for step in payload["steps"]}
    by_key["run_up_acceleration"].update({
        "status": "fault", "coaching_classification": "fault",
        "observation": "Visible loss of rhythm through the final strides.",
    })
    by_key["peak_approach_velocity"].update({
        "status": "ok", "coaching_classification": "opportunity",
        "observation": "A small posture adjustment may improve consistency.",
    })
    by_key["pre_delivery_stride"].update({
        "status": "ok", "coaching_classification": "effective_variation",
        "observation": "A compact stride pattern remains controlled and repeatable.",
    })

    result = normalise_model_payload(payload, duration=4.0)
    steps = {step["key"]: step for step in result["steps"]}

    assert steps["run_up_acceleration"]["status"] == "fault"
    assert steps["run_up_acceleration"]["coaching_classification"] == "fault"
    assert steps["peak_approach_velocity"]["coaching_classification"] == "opportunity"
    assert steps["pre_delivery_stride"]["coaching_classification"] == "effective_variation"


def test_fault_status_cannot_conflict_with_opportunity_or_effective_variation():
    payload = valid_payload()
    by_key = {step["key"]: step for step in payload["steps"]}
    by_key["run_up_acceleration"].update({
        "status": "fault", "coaching_classification": "effective_variation",
        "observation": "A different but controlled movement pattern.",
    })

    result = normalise_model_payload(payload, duration=4.0)
    step = next(step for step in result["steps"] if step["key"] == "run_up_acceleration")

    assert step["status"] == "ok"
    assert step["coaching_classification"] == "effective_variation"


def test_unassessable_step_cannot_keep_a_coaching_classification():
    payload = valid_payload()
    by_key = {step["key"]: step for step in payload["steps"]}
    by_key["run_up_acceleration"].update({
        "status": "not_visible", "t": None, "coaching_classification": "fault",
    })

    result = normalise_model_payload(payload, duration=4.0)
    step = next(step for step in result["steps"] if step["key"] == "run_up_acceleration")

    assert step["status"] == "not_visible"
    assert step["coaching_classification"] == "none"


def test_coaching_priorities_rank_faults_before_optional_opportunities_and_cap_at_three():
    payload = valid_payload()
    by_key = {step["key"]: step for step in payload["steps"]}
    for key, score in (("run_up_acceleration", 4), ("peak_approach_velocity", 5),
                       ("pre_delivery_stride", 6), ("take_off", 3)):
        by_key[key].update({"status": "fault", "coaching_classification": "fault",
                            "score": score, "observation": "A clearly visible technical issue."})
    by_key["gather"].update({"status": "ok", "coaching_classification": "opportunity",
                             "score": 2, "cue": "Refine the hand position.", "observation": "A possible refinement."})
    payload["faults"] = [
        {"title": "Lower priority fault", "phase": "run_up", "step_key": "run_up_acceleration",
         "severity": "low", "description": "Low-severity issue.", "fix": "Build rhythm."},
        {"title": "High priority fault", "phase": "load", "step_key": "take_off",
         "severity": "high", "description": "Higher-severity issue.", "fix": "Control the bound."},
        {"title": "Medium priority fault", "phase": "run_up", "step_key": "peak_approach_velocity",
         "severity": "medium", "description": "Medium-severity issue.", "fix": "Maintain approach speed."},
        {"title": "Another medium fault", "phase": "run_up", "step_key": "pre_delivery_stride",
         "severity": "medium", "description": "Another medium issue.", "fix": "Keep transition smooth."},
    ]

    result = normalise_model_payload(payload, duration=4.0)
    priorities = result["coaching_priorities"]

    assert len(priorities) == 2
    assert [item["title"] for item in priorities] == [
        "High priority fault", "Medium priority fault",
    ]
    assert [item["priority"] for item in priorities] == [1, 2]
    assert all(item["type"] == "fault" for item in priorities)


def test_coaching_priorities_exclude_effective_variations_and_unanchored_findings():
    payload = valid_payload()
    by_key = {step["key"]: step for step in payload["steps"]}
    by_key["run_up_acceleration"].update({
        "status": "ok", "coaching_classification": "effective_variation",
        "cue": "Do not change an effective movement pattern.",
    })
    by_key["peak_approach_velocity"].update({
        "status": "ok", "coaching_classification": "opportunity",
        "cue": "Try a smoother speed build.", "observation": "Optional refinement.",
    })
    by_key["pre_delivery_stride"].update({
        "status": "ok", "coaching_classification": "opportunity",
        "t": None, "cue": "This must not be prioritised.",
    })

    result = normalise_model_payload(payload, duration=4.0)
    priorities = result["coaching_priorities"]

    assert len(priorities) == 1
    assert priorities[0]["type"] == "opportunity"
    assert priorities[0]["step_key"] == "peak_approach_velocity"


def test_synced_evidence_rebuilds_priorities_after_dropping_unanchored_fault():
    payload = valid_payload()
    target = next(step for step in payload["steps"] if step["key"] == "front_knee_bracing")
    target.update({"status": "fault", "coaching_classification": "fault"})
    payload["faults"] = [{
        "title": "Front knee fault", "phase": "front_foot", "step_key": "front_knee_bracing",
        "severity": "high", "description": "Visible knee collapse.", "fix": "Build front-leg strength.",
    }]
    result = normalise_model_payload(payload, duration=4.0)
    next(step for step in result["steps"] if step["key"] == "front_knee_bracing")["t"] = None

    result = reconcile_synced_evidence(result)

    assert result["faults"] == []
    assert result["coaching_priorities"] == []


def test_coaching_guidance_is_attached_only_to_exact_priorities_and_survives_evidence_reconciliation():
    payload = valid_payload()
    target = next(step for step in payload["steps"] if step["key"] == "front_knee_bracing")
    target.update({"status": "fault", "coaching_classification": "fault"})
    payload["faults"] = [{
        "title": "Front knee fault", "phase": "front_foot", "step_key": "front_knee_bracing",
        "severity": "medium", "description": "Visible loss of front-leg position.", "fix": "Work on a stable front leg.",
    }]
    payload["coaching_guidance"] = [
        {"step_key": "front_knee_bracing", "why_it_matters": "A stable base may help transfer momentum consistently.",
         "feel_cue": "Feel the front side firm up at contact.",
         "drill": "This model suggestion must not override the vetted drill.",
         "success_check": "This model success check must not override the vetted check."},
        {"step_key": "run_up_acceleration", "why_it_matters": "This is not a selected priority."},
        {"step_key": "not_a_real_step", "drill": "Ignore this."},
    ]

    result = normalise_model_payload(payload, duration=4.0)
    assert len(result["coaching_priorities"]) == 1
    priority = result["coaching_priorities"][0]
    assert priority["step_key"] == "front_knee_bracing"
    assert priority["why_it_matters"].startswith("A stable base")
    assert priority["feel_cue"].startswith("Feel the front side")
    assert priority["drill_name"] == "Front-leg support progression"
    assert "controlled knee bend" in priority["drill_action"]
    assert priority["drill_dose"].startswith("2 sets of 4")
    assert priority["success_check"].startswith("The front leg supports the finish")

    result["steps"][-1]["t"] = None
    result = reconcile_synced_evidence(result)
    assert result["coaching_priorities"][0]["drill_name"] == "Front-leg support progression"


def test_coaching_guidance_is_removed_when_its_priority_loses_timestamped_evidence():
    payload = valid_payload()
    target = next(step for step in payload["steps"] if step["key"] == "front_knee_bracing")
    target.update({"status": "fault", "coaching_classification": "fault"})
    payload["faults"] = [{
        "title": "Front knee fault", "phase": "front_foot", "step_key": "front_knee_bracing",
        "severity": "high", "description": "Visible issue.", "fix": "Improve control.",
    }]
    payload["coaching_guidance"] = [{
        "step_key": "front_knee_bracing", "drill": "A drill that must disappear."
    }]
    result = normalise_model_payload(payload, duration=4.0)
    target_result = next(step for step in result["steps"] if step["key"] == "front_knee_bracing")
    target_result["t"] = None

    result = reconcile_synced_evidence(result)

    assert result["coaching_priorities"] == []


def test_model_drill_is_not_used_for_steps_without_a_vetted_specific_drill():
    payload = valid_payload()
    target = next(step for step in payload["steps"] if step["key"] == "counter_rotation")
    target.update({"status": "fault", "coaching_classification": "fault"})
    payload["faults"] = [{
        "title": "Rotation concern", "phase": "back_foot", "step_key": "counter_rotation",
        "severity": "medium", "description": "Visible pattern needs expert review.", "fix": "Do not force a change.",
    }]
    payload["coaching_guidance"] = [{
        "step_key": "counter_rotation", "drill": "Generic forced rotation drill",
        "why_it_matters": "A visible pattern may warrant review from a rear view.",
    }]

    result = normalise_model_payload(payload, duration=4.0)

    priority = result["coaching_priorities"][0]
    assert priority["step_key"] == "counter_rotation"
    assert priority["why_it_matters"].startswith("A visible pattern")
    assert "drill" not in priority
    assert "drill_name" not in priority
    assert "success_check" not in priority
