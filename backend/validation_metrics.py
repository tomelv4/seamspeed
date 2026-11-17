"""Evaluate automatic bowling event times against manually annotated reference frames.

Run from the repository root:
  python backend/evaluate_validation.py --pose pose.json --annotation annotation.json
"""
import argparse
import json
from pathlib import Path
from typing import Any

from biomech import Track, detect_events

DEFAULT_TOLERANCE_SECONDS = {"take_off": 0.06, "bfc": 0.05, "ffc": 0.05, "release": 0.04}


def evaluate_event_times(detected: dict[str, Any], reference: dict[str, Any], fps: float = 30.0,
                         tolerances: dict[str, float] | None = None) -> dict[str, Any]:
    """Compare detector times with manual labels; misses count as misses, never as zero error."""
    limits = {**DEFAULT_TOLERANCE_SECONDS, **(tolerances or {})}
    per_event, errors = {}, []
    hits = misses = labelled = 0
    for key in ("take_off", "bfc", "ffc", "release"):
        expected = reference.get(key)
        if expected is None:
            per_event[key] = {"status": "not_labelled"}
            continue
        labelled += 1
        actual = detected.get(key)
        if actual is None:
            misses += 1
            per_event[key] = {"status": "missed", "reference_s": float(expected)}
            continue
        error = abs(float(actual) - float(expected))
        errors.append(error)
        tolerance = max(float(limits.get(key, 1.0 / max(fps, 1.0))), 1.0 / max(fps, 1.0))
        within = error <= tolerance
        hits += int(within)
        per_event[key] = {
            "status": "within_tolerance" if within else "outside_tolerance",
            "detected_s": round(float(actual), 4), "reference_s": round(float(expected), 4),
            "absolute_error_s": round(error, 4), "tolerance_s": round(tolerance, 4),
            "method": detected.get("event_methods", {}).get(key, "unspecified"),
        }
    return {
        "labelled_events": labelled, "detected_events": len(errors), "missed_events": misses,
        "within_tolerance": hits, "within_tolerance_rate": round(hits / labelled, 3) if labelled else None,
        "mean_absolute_error_s": round(sum(errors) / len(errors), 4) if errors else None,
        "events": per_event,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate PACED event detection against manual labels.")
    parser.add_argument("--pose", required=True, help="JSON file containing extracted pose data")
    parser.add_argument("--annotation", required=True, help="JSON file containing bowling_arm, fps and event labels")
    args = parser.parse_args()
    pose = json.loads(Path(args.pose).read_text())
    annotation = json.loads(Path(args.annotation).read_text())
    track = Track(pose, annotation.get("bowling_arm", "right"))
    detected = detect_events(track)
    result = evaluate_event_times(detected, annotation.get("events", {}),
                                  fps=float(annotation.get("fps") or pose.get("sampled_fps") or 30),
                                  tolerances=annotation.get("tolerances"))
    result["detected_event_methods"] = detected.get("event_methods", {})
    result["clip_id"] = annotation.get("clip_id", Path(args.pose).stem)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
