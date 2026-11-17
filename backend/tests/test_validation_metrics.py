import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from validation_metrics import evaluate_event_times


def test_evaluate_event_times_reports_error_and_tolerance():
    result = evaluate_event_times(
        {"bfc": 1.02, "ffc": 1.48, "release": 1.61},
        {"bfc": 1.0, "ffc": 1.5, "release": 1.6},
        fps=30,
    )
    assert result["labelled_events"] == 3
    assert result["detected_events"] == 3
    assert result["missed_events"] == 0
    assert result["within_tolerance"] == 3
    assert result["mean_absolute_error_s"] == 0.0233


def test_missing_event_counts_as_miss_not_zero_error():
    result = evaluate_event_times(
        {"bfc": 1.0},
        {"bfc": 1.0, "ffc": 1.5, "release": 1.6},
    )
    assert result["missed_events"] == 2
    assert result["within_tolerance"] == 1
    assert result["mean_absolute_error_s"] == 0.0


def test_unlabelled_events_are_excluded():
    result = evaluate_event_times({"bfc": 1.0}, {})
    assert result["labelled_events"] == 0
    assert result["within_tolerance_rate"] is None


def test_custom_tolerance_can_be_set_per_event():
    result = evaluate_event_times(
        {"release": 1.08},
        {"release": 1.0},
        fps=60,
        tolerances={"release": 0.1},
    )
    assert result["within_tolerance"] == 1
