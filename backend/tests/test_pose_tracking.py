"""Unit tests for elapsed-time-aware pose track association."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pose


def _detection():
    return {
        "box": np.array([10.0, 10.0, 50.0, 100.0]),
        "kp": np.zeros((17, 2), dtype=float),
        "sc": np.ones(17, dtype=float),
    }


def test_link_associates_nearby_frames_within_time_window():
    tracks = pose._link([[_detection()], [_detection()]], 200.0, times=[0.0, 0.1])
    assert len(tracks) == 1
    assert sorted(tracks[0]["dets"]) == [0, 1]


def test_link_does_not_bridge_long_elapsed_gap_at_low_frame_rate():
    tracks = pose._link([[_detection()], [_detection()]], 200.0, times=[0.0, 0.8])
    assert len(tracks) == 2
    assert all(len(track["dets"]) == 1 for track in tracks)


def test_link_without_timestamps_uses_sixty_fps_default():
    tracks = pose._link([[_detection()], [_detection()]], 200.0)
    assert len(tracks) == 1

def _track(frame_indices):
    return {"dets": {frame: _detection() for frame in frame_indices}}


def test_subject_selection_ignores_tracks_without_shared_observed_frames():
    selected = _track([0, 2, 4])
    disjoint = _track([1, 3, 5])
    result = pose._subject_selection_confidence([selected, disjoint], selected, 200.0)
    assert result == {"confidence": "high", "competing_tracks": 0}


def test_subject_selection_counts_tracks_with_shared_observed_frames():
    selected = _track([0, 2, 4])
    competitor = _track([2, 4, 6])
    result = pose._subject_selection_confidence([selected, competitor], selected, 200.0)
    assert result["competing_tracks"] == 1
    assert result["confidence"] == "low"



def test_pose_serialisation_keeps_raw_measurements_separate_from_smoothed_display():
    raw = np.array([[10.0, 20.0], [30.0, 40.0]], dtype=float)
    display = np.array([[12.0, 18.0], [32.0, 38.0]], dtype=float)
    scores = np.array([0.9, 0.8], dtype=float)

    frame = pose._serialise_pose_keypoints(raw, display, scores, 100, 200)

    assert frame["k"] == [[0.1, 0.1, 0.9], [0.3, 0.2, 0.8]]
    assert frame["display_k"] == [[0.12, 0.09, 0.9], [0.32, 0.19, 0.8]]
    assert frame["k"] != frame["display_k"]


def test_pose_serialisation_does_not_mutate_raw_coordinates():
    raw = np.array([[10.0, 20.0]], dtype=float)
    original = raw.copy()
    display = np.array([[15.0, 25.0]], dtype=float)

    pose._serialise_pose_keypoints(raw, display, np.array([0.9]), 100, 100)

    np.testing.assert_array_equal(raw, original)



def test_display_smoothing_does_not_pull_observed_pose_toward_missing_frame():
    kps = np.array([
        [[10.0, 10.0]],
        [[12.0, 10.0]],
        [[0.0, 0.0]],
        [[16.0, 10.0]],
    ])
    scores = np.ones((4, 1), dtype=float)
    observed = np.array([True, True, False, True])

    smoothed = pose._smooth(kps, scores, observed=observed)

    np.testing.assert_array_equal(smoothed[1], kps[1])
    np.testing.assert_array_equal(smoothed[2], kps[2])


def test_display_smoothing_does_not_change_low_confidence_joint():
    kps = np.array([
        [[10.0, 10.0], [10.0, 20.0]],
        [[11.0, 10.0], [11.0, 20.0]],
        [[12.0, 10.0], [12.0, 20.0]],
    ])
    scores = np.array([[0.9, 0.1], [0.9, 0.1], [0.9, 0.1]])
    observed = np.array([True, True, True])

    smoothed = pose._smooth(kps, scores, observed=observed)

    np.testing.assert_array_equal(smoothed[1, 1], kps[1, 1])
    assert not np.shares_memory(smoothed, kps)


def test_display_smoothing_preserves_fast_joint_motion():
    kps = np.array([
        [[10.0, 10.0]],
        [[20.0, 10.0]],
        [[80.0, 10.0]],
    ])
    scores = np.ones((3, 1), dtype=float)

    smoothed = pose._smooth(kps, scores)

    np.testing.assert_array_equal(smoothed[1], kps[1])
