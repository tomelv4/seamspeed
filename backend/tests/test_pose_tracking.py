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
