"""Defensive parsing and normalisation for multimodal model analysis responses.

The model is an assistant, not a trusted schema validator. This module converts its output
into the stable shape consumed by the API and marks unsupported steps as not assessable.
"""
import json
import math
from datetime import datetime, timedelta, timezone
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




def _build_coaching_priorities(steps: list[dict], faults: list[dict], limit: int = 2) -> list[dict]:
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



STEP_SPECIFIC_DRILLS = {
    "run_up_acceleration": {
        "name": "Progressive run-up rhythm",
        "setup": "Mark your normal starting point and delivery crease; keep the same run-up length.",
        "action": "Complete two walk-throughs, then four run-ups building gradually from easy to normal pace. Focus on an even rhythm rather than sprinting.",
        "dose": "6 run-throughs; rest fully between efforts.",
        "success_check": "Your final steps flow into the bound without a visible stutter or sudden braking across three side-on clips.",
    },
    "peak_approach_velocity": {
        "name": "Controlled build-in",
        "setup": "Use your usual run-up marks and a clear, safe run-off.",
        "action": "Build speed progressively through the approach and run through the crease without delivering the ball. Keep the approach controlled and repeatable.",
        "dose": "4 run-throughs at comfortable intensity, with full recovery.",
        "success_check": "The approach looks progressively faster without a late reach, stumble or obvious deceleration.",
    },
    "pre_delivery_stride": {
        "name": "Last-three-step transition",
        "setup": "Use your normal run-up and identify the final three steps on video.",
        "action": "Rehearse the final three steps at walking pace, then at half pace, letting the bound emerge naturally instead of forcing a longer step.",
        "dose": "2 sets of 4 walk-throughs; stop if the rhythm deteriorates.",
        "success_check": "The final running step transitions into take-off smoothly and consistently.",
    },
    "take_off": {
        "name": "Three-step bound rehearsal",
        "setup": "Start three comfortable steps behind your usual take-off point on a clear, level surface.",
        "action": "Walk in, perform your natural bound and land in a balanced gather. Do not chase extra jump height or distance.",
        "dose": "2 sets of 4 repetitions with a short reset between reps.",
        "success_check": "You can repeat the bound and gather without an uncontrolled landing or loss of balance.",
    },
    "gather": {
        "name": "Gather-and-freeze walk-through",
        "setup": "Use a three-step approach at low intensity with no ball.",
        "action": "Move through your normal gather, pause briefly in the position you naturally arrive in, then step through. Do not force a textbook arm or trunk position.",
        "dose": "2 sets of 4 repetitions.",
        "success_check": "The gather is balanced and repeatable, with no extra adjustment step before back-foot contact.",
    },
    "front_arm_elevation": {
        "name": "Front-arm rhythm rehearsal",
        "setup": "Stand in your normal delivery stance, then progress to a slow walk-in.",
        "action": "Rehearse the front arm moving in time with your gather and delivery. Keep the path comfortable; do not force the hand higher or pull aggressively.",
        "dose": "2 sets of 5 shadow repetitions, then 4 easy walk-ins.",
        "success_check": "The front arm contributes to a repeatable rhythm without disrupting balance or timing.",
    },
    "delivery_stride": {
        "name": "Repeatable landing-zone drill",
        "setup": "Film three comfortable deliveries and note your natural front-foot landing area; place a flat marker beside that area, never where it could be stepped on.",
        "action": "Use a short walk-in and aim to land in your own repeatable zone. Do not lengthen the stride to hit an arbitrary body-height ratio.",
        "dose": "2 sets of 4 walk-in deliveries at easy intensity.",
        "success_check": "Front-foot contact returns to a similar area without reaching or losing control.",
    },
    "front_knee_bracing": {
        "name": "Front-leg support progression",
        "setup": "Start with a short step into your normal front-foot landing position on a non-slip surface.",
        "action": "Accept the landing with a controlled knee bend, hold your balance for two seconds, then progress to a three-step walk-in delivery. Do not force the knee to lock straight.",
        "dose": "2 sets of 4 step-and-holds, then 4 easy walk-ins if comfortable.",
        "success_check": "The front leg supports the finish with less visible collapse while retaining a natural amount of knee flexion.",
    },
    "front_arm_pull_down": {
        "name": "Front-arm timing walk-through",
        "setup": "Use a no-ball shadow action at half speed, viewed from the same camera angle as the analysis.",
        "action": "Move from front-foot contact through trunk turn while allowing the front arm to fold naturally. Avoid yanking the arm down or forcing the shoulders to rotate.",
        "dose": "2 sets of 5 slow repetitions, then 4 easy walk-throughs.",
        "success_check": "The front arm moves in time with the rest of the action without a sudden isolated pull.",
    },
    "arm_follow_through": {
        "name": "Natural arm-finish drill",
        "setup": "Use a three-step walk-in with a soft ball or shadow action in a clear space.",
        "action": "Complete the delivery movement at easy intensity and allow the bowling arm to continue its natural path after release. Do not deliberately stop or wrench the arm.",
        "dose": "2 sets of 4 controlled repetitions.",
        "success_check": "The arm finishes smoothly and the bowler remains balanced after the delivery.",
    },
    "back_leg_swing": {
        "name": "Balanced finish walk-through",
        "setup": "Start with a slow shadow delivery on a level, non-slip surface.",
        "action": "Move through front-foot contact and allow the rear leg to follow its natural path while you regain balance. Do not force a particular leg height or direction.",
        "dose": "2 sets of 5 repetitions.",
        "success_check": "The rear leg follows through without an extra recovery hop or uncontrolled sideways step.",
    },
    "deceleration_strides": {
        "name": "Controlled run-off rehearsal",
        "setup": "Use a clear, unobstructed run-off area beyond the crease.",
        "action": "Complete a low-intensity walk-in delivery and continue moving naturally after release, reducing speed over several comfortable steps.",
        "dose": "4 repetitions with full walk-back recovery.",
        "success_check": "You decelerate under control and remain within the available run-off space.",
    },
}


def _attach_coaching_guidance(priorities: list[dict], raw_guidance: Any) -> list[dict]:
    """Attach exact-step coaching explanation and a vetted step-specific drill."""
    guidance_by_key = {}
    if isinstance(raw_guidance, list):
        for item in raw_guidance:
            if not isinstance(item, dict) or not isinstance(item.get("step_key"), str):
                continue
            key = item["step_key"]
            if key in guidance_by_key:
                continue
            guidance_by_key[key] = {
                field: value.strip()[:500]
                for field in ("why_it_matters", "feel_cue")
                if isinstance((value := item.get(field)), str) and value.strip()
            }

    enriched = []
    for priority in priorities:
        key = priority["step_key"]
        item = {**priority, **guidance_by_key.get(key, {})}
        drill = STEP_SPECIFIC_DRILLS.get(key)
        if drill:
            item.update({
                "drill_name": drill["name"],
                "drill_setup": drill["setup"],
                "drill_action": drill["action"],
                "drill_dose": drill["dose"],
                "success_check": drill["success_check"],
            })
            item["drill"] = f'{drill["name"]}: {drill["action"]} {drill["dose"]}'
        else:
            # A generic model-generated drill is less useful than honestly withholding one.
            item.pop("drill", None)
            item.pop("drill_name", None)
            item.pop("drill_setup", None)
            item.pop("drill_action", None)
            item.pop("drill_dose", None)
            item.pop("success_check", None)
        enriched.append(item)
    return enriched

def build_recurring_fault_history(analyses: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    """Count only faults tied to a timestamped, explicitly fault-classified step."""
    grouped: dict[str, dict[str, Any]] = {}
    for analysis in analyses:
        view = analysis.get("camera_view")
        if view not in VALID_CAMERA_VIEWS - {"unknown"}:
            continue
        if analysis.get("camera_view_confidence") not in {"high", "medium"}:
            continue
        steps = {
            step.get("key"): step for step in analysis.get("steps", [])
            if isinstance(step, dict) and step.get("key")
        }
        seen_in_analysis: set[str] = set()
        for fault in analysis.get("faults", []):
            if not isinstance(fault, dict):
                continue
            key = fault.get("step_key")
            step = steps.get(key)
            if (not key or key in seen_in_analysis or not step
                    or step.get("status") != "fault"
                    or step.get("coaching_classification") != "fault"
                    or step.get("t") is None
                    or step.get("evidence_level") == "insufficient"):
                continue
            seen_in_analysis.add(key)
            group_key = f"{key}:{view}"
            item = grouped.setdefault(group_key, {
                "step_key": key,
                "title": fault.get("title") or step.get("name") or key.replace("_", " ").title(),
                "count": 0,
                "last_seen": analysis.get("created_at"),
                "camera_view": view,
            })
            item["count"] += 1
            if (analysis.get("created_at") or "") > (item.get("last_seen") or ""):
                item["last_seen"] = analysis.get("created_at")
                item["camera_view"] = view
                item["title"] = fault.get("title") or step.get("name") or key.replace("_", " ").title()
    return sorted(grouped.values(), key=lambda item: (-item["count"], item["title"]))[:limit]


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
    payload["coaching_priorities"] = _attach_coaching_guidance(_build_coaching_priorities(steps, payload["faults"]), payload.get("coaching_guidance"))
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
        "coaching_priorities": _attach_coaching_guidance(_build_coaching_priorities(steps, faults), payload.get("coaching_guidance")),
        "strengths": text_list(payload.get("strengths")),
        "tips": text_list(payload.get("tips")),
    }



def build_training_response_summary(sessions: list[dict], now: datetime | None = None) -> dict:
    """Summarise recent *logged* gym/recovery responses without treating plans as completed work."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=14)
    recent = []
    for session in sessions:
        if not isinstance(session, dict) or session.get("status") != "ended":
            continue
        plan = session.get("plan") if isinstance(session.get("plan"), dict) else {}
        mode = plan.get("session_mode")
        completion = session.get("completion") if isinstance(session.get("completion"), dict) else {}
        if mode not in {"gym", "recovery"} or not completion.get("logged_at"):
            continue
        raw_date = session.get("ended_at") or completion.get("logged_at") or session.get("created_at")
        try:
            observed_at = datetime.fromisoformat(str(raw_date).replace("Z", "+00:00"))
            if observed_at.tzinfo is None:
                observed_at = observed_at.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if observed_at < cutoff or observed_at > now + timedelta(days=1):
            continue
        planned = [item for item in plan.get("activities", []) if isinstance(item, dict)]
        logged = [item for item in completion.get("activities", []) if isinstance(item, dict)]
        completed = [item for item in logged if item.get("completed") is True]
        recent.append({
            "date": observed_at.date().isoformat(),
            "mode": mode,
            "completed_activities": len(completed),
            "logged_activities": len(logged),
            "planned_activities": len(planned),
            "completion_ratio": round(len(completed) / len(planned), 2) if planned else None,
            "session_effort": completion.get("session_effort"),
            "overall_feeling": completion.get("overall_feeling"),
            "actual_sets_logged": sum(
                int(item["actual_sets"]) for item in completed
                if isinstance(item.get("actual_sets"), int) and not isinstance(item.get("actual_sets"), bool)
            ),
        })
    recent.sort(key=lambda item: item["date"], reverse=True)
    recent = recent[:5]
    if not recent:
        return {
            "window_days": 14, "logged_sessions": 0, "sessions": [],
            "adjustment": "no_recent_response_data",
            "guidance": "No completed gym or recovery response has been logged in the last 14 days. Do not assume readiness or progress; keep the requested plan conservative and ask the bowler how they feel.",
        }

    latest = recent[0]
    high_response = [
        item for item in recent[:3]
        if item["overall_feeling"] == "rough"
        or item["overall_feeling"] == "tired" and item["session_effort"] == "hard"
        or item["session_effort"] == "hard" and item["overall_feeling"] in {"tired", "rough"}
    ]
    low_completion = [item for item in recent[:3] if item["completion_ratio"] is not None and item["completion_ratio"] <= 0.5]
    if latest["overall_feeling"] == "rough" or len(high_response) >= 2:
        adjustment = "reduce_next_gym_load"
        guidance = "Recent logged sessions show a rough post-session response or repeated hard sessions with fatigue. Keep the next gym session low intensity, reduce optional sets, avoid progression, and prioritise recovery. Ask about current readiness before hard bowling."
    elif len(low_completion) >= 2:
        adjustment = "hold_or_reduce_volume"
        guidance = "Recent logs show that half or fewer of planned activities were completed in at least two sessions. Do not increase training volume; repeat a shorter achievable session or reduce optional work and check whether the plan fits the bowler's schedule."
    elif len(recent) >= 2 and all(
        item["overall_feeling"] == "fresh" and item["session_effort"] in {"easy", "moderate"}
        and item["completion_ratio"] is not None and item["completion_ratio"] >= 0.8
        for item in recent[:2]
    ):
        adjustment = "progress_only_if_ready"
        guidance = "The latest two logged sessions were mostly completed with easy/moderate effort and a fresh response. A small progression may be considered only if current readiness and movement quality remain good; do not automatically add sets or bowling volume."
    else:
        adjustment = "maintain_and_review"
        guidance = "Recent responses are mixed or incomplete. Maintain the requested training volume, avoid automatic progression, and ask the bowler about current readiness before hard sessions."
    return {
        "window_days": 14,
        "logged_sessions": len(recent),
        "sessions": recent,
        "adjustment": adjustment,
        "guidance": guidance,
    }



def _development_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (TypeError, ValueError):
        return None


def build_development_overview(
    analyses: list[dict],
    workload_entries: list[dict],
    training_sessions: list[dict],
    drill_completions: list[dict],
    now: datetime | None = None,
) -> dict:
    """Build a 28-day athlete development snapshot from explicitly logged records only."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=28)

    def in_window(value: Any) -> datetime | None:
        parsed = _development_datetime(value)
        return parsed if parsed and cutoff <= parsed <= now + timedelta(days=1) else None

    bowling_logs = []
    for entry in workload_entries:
        observed = in_window(entry.get("date") or entry.get("created_at"))
        balls = entry.get("balls")
        if observed and isinstance(balls, int) and not isinstance(balls, bool):
            bowling_logs.append((observed, max(0, balls)))

    gym_records, recovery_records = [], []
    activity = []
    for session in training_sessions:
        if not isinstance(session, dict) or session.get("status") != "ended":
            continue
        plan = session.get("plan") if isinstance(session.get("plan"), dict) else {}
        mode = plan.get("session_mode")
        completion = session.get("completion") if isinstance(session.get("completion"), dict) else {}
        observed = in_window(completion.get("logged_at"))
        if mode not in {"gym", "recovery"} or not observed:
            continue
        planned = [item for item in plan.get("activities", []) if isinstance(item, dict)]
        logged = [item for item in completion.get("activities", []) if isinstance(item, dict)]
        completed = [item for item in logged if item.get("completed") is True]
        record = {
            "date": observed.date().isoformat(), "mode": mode,
            "completed_activities": len(completed), "planned_activities": len(planned),
            "effort": completion.get("session_effort"), "feeling": completion.get("overall_feeling"),
            "actual_sets": sum(int(item["actual_sets"]) for item in completed
                               if isinstance(item.get("actual_sets"), int) and not isinstance(item.get("actual_sets"), bool)),
        }
        (gym_records if mode == "gym" else recovery_records).append(record)
        activity.append({"date": observed.isoformat(), "kind": mode, "title": mode.title() + " session",
                         "detail": str(len(completed)) + " of " + str(len(planned)) + " activities logged as completed"})

    practice = []
    for item in drill_completions:
        observed = in_window(item.get("completed_at"))
        if observed:
            practice.append((observed, item))
            activity.append({"date": observed.isoformat(), "kind": "practice",
                              "title": item.get("drill_name") or "Coaching drill",
                              "detail": item.get("focus") or "Targeted technique practice"})

    video_analyses = []
    for item in analyses:
        if not isinstance(item, dict) or item.get("is_bowling_video") is False:
            continue
        observed = in_window(item.get("created_at"))
        if observed:
            video_analyses.append(item)
            view = str(item.get("camera_view") or "Camera view unavailable").replace("_", " ")
            activity.append({"date": observed.isoformat(), "kind": "video", "title": "Video analysis", "detail": view})

    for observed, balls in bowling_logs:
        activity.append({"date": observed.isoformat(), "kind": "bowling",
                         "title": "Bowling workload logged", "detail": str(balls) + " deliveries"})

    activity.sort(key=lambda item: item["date"], reverse=True)
    bowling_days = len({observed.date().isoformat() for observed, balls in bowling_logs if balls > 0})
    recent_practice = sorted(practice, key=lambda x: x[0], reverse=True)
    return {
        "window_days": 28,
        "bowling": {"deliveries": sum(balls for _, balls in bowling_logs), "logged_days": bowling_days,
                    "entries": len(bowling_logs)},
        "gym": {"sessions": len(gym_records), "activities_completed": sum(item["completed_activities"] for item in gym_records),
                "actual_sets": sum(item["actual_sets"] for item in gym_records),
                "recent": sorted(gym_records, key=lambda x: x["date"], reverse=True)[:3]},
        "recovery": {"sessions": len(recovery_records),
                     "activities_completed": sum(item["completed_activities"] for item in recovery_records),
                     "recent": sorted(recovery_records, key=lambda x: x["date"], reverse=True)[:3]},
        "practice": {"drill_completions": len(practice),
                     "recent_focuses": list(dict.fromkeys(
                         (item.get("focus") or item.get("drill_name") or "Technique practice")
                         for _, item in recent_practice
                     ))[:4]},
        "video": {"analyses": len(video_analyses)},
        "recent_activity": activity[:8],
    }


def attach_practice_to_step_trends(trends: list[dict], drill_completions: list[dict]) -> list[dict]:
    """Attach exact-step practice logged between comparable observations; not a causal claim."""
    parsed = []
    for completion in drill_completions:
        if not isinstance(completion, dict) or not completion.get("step_key"):
            continue
        completed_at = _development_datetime(completion.get("completed_at"))
        if completed_at:
            parsed.append((completed_at, completion))
    output = []
    for trend in trends:
        previous_at = _development_datetime(trend.get("previous_date"))
        current_at = _development_datetime(trend.get("current_date"))
        if not previous_at or not current_at or current_at <= previous_at:
            output.append({**trend, "practice_between_count": 0, "practice_drill_names": [], "practice_last_date": None})
            continue
        matching = [(when, item) for when, item in parsed
                    if item.get("step_key") == trend.get("step_key") and previous_at < when <= current_at]
        matching.sort(key=lambda pair: pair[0])
        names = list(dict.fromkeys(str(item.get("drill_name")).strip() for _, item in matching
                                   if item.get("drill_name") and str(item.get("drill_name")).strip()))
        output.append({**trend, "practice_between_count": len(matching),
                       "practice_drill_names": names[:3],
                       "practice_last_date": matching[-1][0].isoformat() if matching else None})
    return output