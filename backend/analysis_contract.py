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
VALID_CAMERA_VIEWS = {"side_on", "rear", "front_on", "oblique", "unknown"}
VALID_CONFIDENCE = {"high", "medium", "low"}


def _finite_number(value: Any, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return max(minimum, min(maximum, number))


def parse_model_json(raw: str) -> dict:
    """Decode the first JSON object even when the model adds fences or a short preamble."""
    if not isinstance(raw, str):
        raise ValueError("The analysis model returned a non-text response.")
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


def normalise_model_payload(payload: dict, duration: float | None = None) -> dict:
    """Validate model fields, clamp numeric ranges and make missing evidence explicit."""
    if not isinstance(payload, dict):
        raise ValueError("The analysis model response must be an object.")

    is_bowling = payload.get("is_bowling_video")
    if not isinstance(is_bowling, bool):
        raise ValueError("The analysis model did not identify whether this is a bowling video.")

    raw_overall = _finite_number(payload.get("overall_score"), 0, 10)
    overall_assessable = raw_overall is not None
    overall_score = raw_overall if raw_overall is not None else 0.0

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
        assessable = score is not None and isinstance(feedback, str) and bool(feedback.strip())
        phases.append({
            "key": key,
            "name": source.get("name") if isinstance(source.get("name"), str) and source.get("name").strip() else name,
            "score": score if score is not None else 0.0,
            "feedback": feedback.strip() if isinstance(feedback, str) and feedback.strip()
                        else "Not enough clear visual evidence to assess this phase.",
            "assessable": assessable,
        })

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
        if status not in VALID_STATUSES or score is None or (status != "not_visible" and not observation.strip()):
            status = "not_visible"
        raw_time = source.get("t")
        timestamp = _finite_number(raw_time, 0, duration_limit if duration_limit is not None else float("inf"))
        if status == "not_visible":
            timestamp = None
            score = 0.0
            observation = observation.strip() or "Not enough clear visual evidence to assess this movement."
            cue = ""
        elif timestamp is not None and timestamp >= last_time:
            last_time = timestamp
        else:
            timestamp = None
        if status != "not_visible":
            assessable_count += 1
        steps.append({
            "key": key, "name": name, "phase": phase, "description": when, "ideal": ideal,
            "t": round(timestamp, 3) if timestamp is not None else None,
            "score": score if score is not None else 0.0, "status": status,
            "observation": observation.strip(), "cue": cue.strip(),
        })

    faults = []
    raw_faults = payload.get("faults") if isinstance(payload.get("faults"), list) else []
    phase_keys = {key for key, _ in PHASES}
    for fault in raw_faults:
        if not isinstance(fault, dict):
            continue
        title = fault.get("title")
        phase = fault.get("phase")
        severity = fault.get("severity")
        description = fault.get("description")
        if (not isinstance(title, str) or not title.strip() or phase not in phase_keys
                or severity not in {"low", "medium", "high"}
                or not isinstance(description, str) or not description.strip()):
            continue
        fix = fault.get("fix") if isinstance(fault.get("fix"), str) else ""
        faults.append({
            "title": title.strip(), "phase": phase, "severity": severity,
            "description": description.strip(), "fix": fix.strip(),
        })

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
        "overall_score": round(overall_score, 1),
        "overall_score_assessable": bool(overall_assessable and assessable_count >= 10),
        "summary": summary.strip(),
        "action_type": payload.get("action_type") if isinstance(payload.get("action_type"), str) else "unknown",
        "camera_view": camera_view,
        "camera_view_confidence": camera_confidence,
        "phases": phases,
        "steps": steps,
        "faults": faults,
        "strengths": text_list(payload.get("strengths")),
        "tips": text_list(payload.get("tips")),
    }
