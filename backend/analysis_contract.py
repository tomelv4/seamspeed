"""Defensive parsing and normalisation for multimodal model analysis responses.

The model is an assistant, not a trusted schema validator. This module converts its output
into the stable shape consumed by the API and marks unsupported steps as not assessable.
"""
import json
import math
from typing import Any

from biomech import STEPS

PHASES = (
    ("run_up", "Run-up"),
    ("load", "Load & Bound"),
    ("back_foot", "Back-Foot Contact"),
    ("front_foot", "Front-Foot Contact"),
    ("release", "Release"),
    ("follow_through", "Follow-Through"),
)
VALID_STATUSES = {"good", "ok", "fault", "not_visible"}
VALID_COACHING_CLASSIFICATIONS = {"fault", "opportunity", "effective_variation", "none"}
VALID_CAMERA_VIEWS = {"side_on", "rear", "front_on", "oblique", "unknown"}
VALID_CONFIDENCE = {"high", "medium", "low"}


def _finite_number(value: Any, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return max(minimum, min(maximum, number))


def _valid_timestamp(value: Any, duration: float | None, previous: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    timestamp = float(value)
    if not math.isfinite(timestamp) or timestamp < 0:
        return None
    if duration is not None and timestamp > duration:
        return None
    if timestamp < previous:
        return None
    return timestamp


def parse_model_json(raw: str) -> dict:
    """Decode the first JSON object even when the model adds fences or a short preamble."""
    if not isinstance(raw, str):
        raise ValueError("The analysis model returned a non-text response.")
    if raw.lstrip().startswith("["):
        raise ValueError("The analysis model response must be a JSON object, not an array.")
    start = raw.find("{")
    if start < 0:
        raise ValueError("The analysis model did not return a JSON object.")
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"The analysis model returned invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("The analysis model response must be a JSON object.")
    return payload




def _build_coaching_priorities(steps: list[dict], faults: list[dict], limit: int = 3) -> list[dict]:
    """Rank a small set of actionable, timestamped coaching focuses."""
    by_key = {step.get("key"): step for step in steps if isinstance(step, dict)}
    ranked = []
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    ordered_faults = sorted(
        faults,
        key=lambda fault: (
            severity_rank.get(fault.get("severity"), 3),
            by_key.get(fault.get("step_key"), {}).get("score", 10),
        ),
    )
    seen = set()
    for fault in ordered_faults:
        step = by_key.get(fault.get("step_key"))
        if (not step or step.get("status") != "fault" or step.get("t") is None
                or step.get("coaching_classification") != "fault" or step["key"] in seen):
            continue
        seen.add(step["key"])
        ranked.append({
            "type": "fault", "step_key": step["key"], "phase": step["phase"],
            "title": fault["title"], "reason": fault["description"],
            "action": fault.get("fix") or step.get("cue", ""),
            "severity": fault["severity"],
        })
        if len(ranked) >= limit:
            break

    if len(ranked) < limit:
        opportunities = sorted(
            (step for step in steps if isinstance(step, dict)
             and step.get("coaching_classification") == "opportunity"
             and step.get("status") != "not_visible" and step.get("t") is not None
             and step.get("key") not in seen and step.get("cue")),
            key=lambda step: (step.get("score", 10), step.get("t", 0)),
        )
        for step in opportunities:
            seen.add(step["key"])
            ranked.append({
                "type": "opportunity", "step_key": step["key"], "phase": step["phase"],
                "title": step["name"], "reason": step.get("observation", ""),
                "action": step.get("cue", ""), "severity": None,
            })
            if len(ranked) >= limit:
                break

    return [{"priority": index + 1, **item} for index, item in enumerate(ranked)]


def reconcile_synced_evidence(payload: dict) -> dict:
    """Remove coaching judgements whose exact movement frame could not be anchored."""
    steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if step.get("status") != "not_visible" and step.get("t") is None:
            step["status"] = "not_visible"
            step["score"] = 0.0
            step["observation"] = "The relevant movement moment could not be located reliably in the video."
            step["cue"] = ""
            step["evidence_level"] = "insufficient"
            step["coaching_classification"] = "none"

    phases = payload.get("phases") if isinstance(payload.get("phases"), list) else []
    assessable_phase_count = 0
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        phase_steps = [
            step for step in steps
            if isinstance(step, dict) and step.get("phase") == phase.get("key")
            and step.get("status") != "not_visible" and step.get("t") is not None
        ]
        phase["assessable"] = bool(phase_steps)
        phase["score"] = round(
            sum(float(step.get("score", 0)) for step in phase_steps) / len(phase_steps), 1
        ) if phase_steps else 0.0
        if phase_steps:
            assessable_phase_count += 1
        elif phase.get("feedback") and phase.get("feedback") != "Not enough clear visual evidence to assess this phase.":
            phase["feedback"] = "Not enough timestamped visual evidence to assess this phase."

    assessable_steps = [
        step for step in steps
        if isinstance(step, dict) and step.get("status") != "not_visible" and step.get("t") is not None
    ]
    overall_assessable = len(assessable_steps) >= 10 and assessable_phase_count >= 4
    payload["overall_score_assessable"] = overall_assessable
    payload["overall_score"] = (
        round(sum(phase["score"] for phase in phases if isinstance(phase, dict) and phase.get("assessable"))
              / assessable_phase_count, 1)
        if overall_assessable else 0.0
    )
    if not overall_assessable:
        payload["summary"] = (
            "There is not enough synchronized visual evidence to produce a reliable overall technique score. "
            "Use a clearer recording that keeps the complete delivery visible from a suitable camera angle."
        )
        payload["strengths"] = []
        payload["tips"] = []

    assessable_fault_steps = {
        step["key"]: step for step in assessable_steps if step.get("status") == "fault"
    }
    payload["faults"] = [
        fault for fault in (payload.get("faults") or [])
        if isinstance(fault, dict)
        and fault.get("step_key") in assessable_fault_steps
        and assessable_fault_steps[fault["step_key"]].get("phase") == fault.get("phase")
    ]
    payload["coaching_priorities"] = _build_coaching_priorities(steps, payload["faults"])
    payload["score_method"] = "equal_weight_mean_of_timestamped_assessable_phase_step_scores"
    return payload

def normalise_model_payload(payload: dict, duration: float | None = None) -> dict:
    """Validate model fields, clamp numeric ranges and make missing evidence explicit."""
    if not isinstance(payload, dict):
        raise ValueError("The analysis model response must be an object.")

    is_bowling = payload.get("is_bowling_video")
    if not isinstance(is_bowling, bool):
        raise ValueError("The analysis model did not identify whether this is a bowling video.")

    summary = payload.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = "The video was processed, but the model did not provide a reliable coaching summary."

    duration_limit = None
    if isinstance(duration, (int, float)) and not isinstance(duration, bool):
        if math.isfinite(float(duration)) and float(duration) > 0:
            duration_limit = float(duration)

    raw_phases = payload.get("phases") if isinstance(payload.get("phases"), list) else []
    phase_by_key = {}
    for phase in raw_phases:
        if isinstance(phase, dict) and isinstance(phase.get("key"), str):
            phase_by_key.setdefault(phase["key"], phase)

    phases = []
    for key, name in PHASES:
        source = phase_by_key.get(key, {})
        score = _finite_number(source.get("score"), 0, 10)
        feedback = source.get("feedback")
        assessable = bool(is_bowling and score is not None and isinstance(feedback, str) and feedback.strip())
        phases.append({
            "key": key,
            "name": source.get("name") if isinstance(source.get("name"), str) and source.get("name").strip() else name,
            "score": score if score is not None else 0.0,
            "feedback": feedback.strip() if isinstance(feedback, str) and feedback.strip()
                        else "Not enough clear visual evidence to assess this phase.",
            "assessable": assessable,
        })

    raw_release = payload.get("release_evidence") if isinstance(payload.get("release_evidence"), dict) else {}
    release_confidence = raw_release.get("confidence")
    if release_confidence not in VALID_CONFIDENCE:
        release_confidence = "low"
    ball_separation_visible = raw_release.get("ball_separation_visible") is True and release_confidence in {"high", "medium"}
    release_evidence = {
        "ball_separation_visible": ball_separation_visible,
        "confidence": release_confidence,
        "notes": raw_release.get("notes").strip() if isinstance(raw_release.get("notes"), str) else "",
    }

    raw_steps = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    step_by_key = {}
    for step in raw_steps:
        if isinstance(step, dict) and isinstance(step.get("key"), str):
            step_by_key.setdefault(step["key"], step)

    steps, last_time, assessable_count = [], -1.0, 0
    for key, name, phase, when, ideal in STEPS:
        source = step_by_key.get(key, {})
        status = source.get("status")
        score = _finite_number(source.get("score"), 0, 10)
        observation = source.get("observation") if isinstance(source.get("observation"), str) else ""
        cue = source.get("cue") if isinstance(source.get("cue"), str) else ""
        if key == "finger_roll_release" and not ball_separation_visible:
            status = "not_visible"
        classification = source.get("coaching_classification")
        if classification not in VALID_COACHING_CLASSIFICATIONS:
            classification = "fault" if status == "fault" else "none"
        if status == "fault" and classification != "fault":
            status = "ok"
        if status != "fault" and classification == "fault":
            classification = "none"
        if (not is_bowling or status not in VALID_STATUSES or score is None
                or (status != "not_visible" and not observation.strip())):
            status = "not_visible"
        raw_time = source.get("t")
        timestamp = _valid_timestamp(raw_time, duration_limit, last_time)
        if status == "not_visible":
            timestamp = None
            score = 0.0
            observation = observation.strip() or "Not enough clear visual evidence to assess this movement."
            cue = ""
            classification = "none"
        elif timestamp is not None:
            last_time = timestamp
        if status != "not_visible":
            assessable_count += 1
        steps.append({
            "key": key, "name": name, "phase": phase, "description": when, "ideal": ideal,
            "t": round(timestamp, 3) if timestamp is not None else None,
            "score": score if score is not None else 0.0, "status": status,
            "observation": observation.strip(), "cue": cue.strip(),
            "coaching_classification": classification if status != "not_visible" else "none",
        })

    for phase in phases:
        phase_steps = [
            step["score"] for step in steps
            if step["phase"] == phase["key"] and step["status"] != "not_visible"
        ]
        phase["assessable"] = bool(is_bowling and phase_steps)
        if phase["assessable"] and phase["feedback"] == "Not enough clear visual evidence to assess this phase.":
            phase["feedback"] = "Phase score is calculated from the assessable movement steps."
        phase["score"] = round(sum(phase_steps) / len(phase_steps), 1) if phase["assessable"] else 0.0
    assessable_phase_count = sum(1 for phase in phases if phase["assessable"])
    overall_assessable = is_bowling and assessable_count >= 10 and assessable_phase_count >= 4
    overall_score = (
        round(sum(phase["score"] for phase in phases if phase["assessable"]) / assessable_phase_count, 1)
        if overall_assessable else 0.0
    )

    faults = []
    raw_faults = payload.get("faults") if isinstance(payload.get("faults"), list) else []
    assessable_phase_keys = {phase["key"] for phase in phases if phase["assessable"]}
    phase_keys = {key for key, _ in PHASES}
    for fault in raw_faults:
        if not isinstance(fault, dict):
            continue
        title = fault.get("title")
        phase = fault.get("phase")
        severity = fault.get("severity")
        description = fault.get("description")
        if (not isinstance(title, str) or not title.strip() or phase not in phase_keys or phase not in assessable_phase_keys
                or severity not in {"low", "medium", "high"}
                or not isinstance(description, str) or not description.strip()):
            continue
        phase_steps = [step for step in steps if step["phase"] == phase and step["status"] != "not_visible"]
        if not phase_steps:
            continue
        requested_step = fault.get("step_key")
        valid_step_keys = {step["key"] for step in phase_steps}
        # Never silently attach a fault to an arbitrary step in the same phase.
        if requested_step not in valid_step_keys:
            continue
        step_key = requested_step
        fix = fault.get("fix") if isinstance(fault.get("fix"), str) else ""
        faults.append({
            "title": title.strip(), "phase": phase, "step_key": step_key, "severity": severity,
            "description": description.strip(), "fix": fix.strip(),
        })

    faults.sort(key=lambda fault: {"high": 0, "medium": 1, "low": 2}[fault["severity"]])

    def text_list(value):
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    camera_view = payload.get("camera_view")
    if camera_view not in VALID_CAMERA_VIEWS:
        camera_view = "unknown"
    camera_confidence = payload.get("camera_view_confidence")
    if camera_confidence not in VALID_CONFIDENCE:
        camera_confidence = "low"

    return {
        **payload,
        "is_bowling_video": is_bowling,
        "overall_score": overall_score,
        "overall_score_assessable": bool(overall_assessable),
        "score_method": "equal_weight_mean_of_assessable_phase_step_scores",
        "summary": summary.strip(),
        "action_type": payload.get("action_type") if isinstance(payload.get("action_type"), str) else "unknown",
        "camera_view": camera_view,
        "camera_view_confidence": camera_confidence,
        "release_evidence": release_evidence,
        "phases": phases,
        "steps": steps,
        "faults": faults,
        "coaching_priorities": _build_coaching_priorities(steps, faults),
        "strengths": text_list(payload.get("strengths")),
        "tips": text_list(payload.get("tips")),
    }
