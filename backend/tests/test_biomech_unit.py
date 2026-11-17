# Unit tests for biomech.py: 27-step model, event detection, merge/fallback, step windows, sync_times, measured()
import math
import os
import sys

import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import biomech  # noqa: E402
import pose as pose_lib  # noqa: E402

KEYS = [s[0] for s in biomech.STEPS]
EVENT_STEPS = {"bfc": "bfc", "ffc": "ffc", "take_off": "take_off"}


def _bump(t, t0, t1, a):
    return a * math.sin(math.pi * (t - t0) / (t1 - t0)) if t0 < t < t1 else 0.0


def synth_pose(arm="right", dur=2.5, fps=30, front=(0.833, 1.367), back=(0.9, 1.1), rel=1.5):
    """Side-on bowler: front ankle off ground front[0]..front[1], back ankle back[0]..back[1], bowling wrist peaks at rel."""
    A = biomech.RA if arm == "right" else biomech.LA
    F = biomech.LA if arm == "right" else biomech.RA
    frames = []
    n = int(dur * fps) + 1
    for i in range(n):
        t = round(i / fps, 3)
        x = 0.2 + 0.25 * t  # runs across the frame
        k = [[x, 0.5, 0.9] for _ in range(17)]
        k[0] = [x, 0.3, 0.9]
        for s in (5, 6):
            k[s] = [x, 0.4, 0.9]
        for s in (11, 12):
            k[s] = [x, 0.6, 0.9]
        for s in (13, 14):
            k[s] = [x + 0.01, 0.75, 0.9]
        k[F["ankle"]] = [x + 0.05, 0.9 - _bump(t, *front, 0.12), 0.9]
        k[A["ankle"]] = [x - 0.05, 0.9 - _bump(t, *back, 0.10), 0.9]
        wy = 0.55 - 0.40 * math.exp(-((t - rel) ** 2) / (2 * 0.06 ** 2))
        k[A["wrist"]] = [x + 0.02, wy, 0.9]
        k[A["elbow"]] = [x + 0.01, (0.4 + wy) / 2, 0.9]
        k[F["wrist"]] = [x + 0.05, 0.5, 0.9]
        frames.append({"t": t, "k": k})
    return {"width": 1920, "height": 1080, "frames": frames, "detected": n}


def ai_steps_from(times):
    return [{"key": k, "t": times.get(k), "score": 5, "status": "ok"} for k in KEYS]


class TestStepModel:
    def test_27_unique_steps_with_when_and_ideal(self):
        assert len(biomech.STEPS) == 27 and len(set(KEYS)) == 27
        for key, name, phase, when, ideal in biomech.STEPS:
            assert name and when and ideal, key
            assert phase in {"run_up", "load", "back_foot", "front_foot", "release", "follow_through"}

    def test_windows_cover_all_steps(self):
        assert set(biomech.WINDOWS) == set(KEYS)
        for k, (anchor, a, b) in biomech.WINDOWS.items():
            if b is None:
                assert k in biomech.NEXT, k

    def test_step_list_text(self):
        assert biomech.STEP_LIST_TEXT.count("WHEN:") == 27 and biomech.STEP_LIST_TEXT.count("IDEAL:") == 27


class TestDetectEvents:
    def test_right_arm_synthetic(self):
        ev = biomech.detect_events(biomech.Track(synth_pose("right"), "right"))
        print("events", ev)
        assert ev["release"] == pytest.approx(1.5, abs=0.034)
        assert ev["ffc"] == pytest.approx(1.367, abs=0.034)
        assert ev["bfc"] == pytest.approx(1.1, abs=0.034)
        assert "take_off" not in ev

    def test_left_arm_synthetic(self):
        ev = biomech.detect_events(biomech.Track(synth_pose("left"), "left"))
        assert ev["release"] == pytest.approx(1.5, abs=0.034)
        assert ev["ffc"] == pytest.approx(1.367, abs=0.034)
        assert ev["bfc"] == pytest.approx(1.1, abs=0.034)

    def test_landing_rejects_three_frames_spread_over_long_elapsed_time(self):
        track = biomech.Track(synth_pose("right"), "right")
        # Simulate a sparse/irregular observation sequence around the foot plant.
        # Frame indices are consecutive, but the observations are 200 ms apart.
        track.t[40:] += np.arange(len(track.t) - 40) * 0.2
        assert biomech._landing(track, track.front["ankle"], 0.8, 3.0) is None

    def test_wrong_arm_profile_does_not_crash(self):
        ev = biomech.detect_events(biomech.Track(synth_pose("right"), "left"))
        assert isinstance(ev, dict)

    @pytest.mark.parametrize("arm", [None, "", "unknown", "Right", "Left"])
    def test_track_normalises_missing_or_unrecognised_arm(self, arm):
        track = biomech.Track(synth_pose("right"), arm)
        assert track.arm is (biomech.LA if arm == "Left" else biomech.RA)

    def test_pose_helpers_accept_missing_or_unrecognised_arm(self):
        p = synth_pose("right")
        assert pose_lib.metrics_at(p, 1.0, None)
        assert "t=" in pose_lib.timeline_text(p, "unrecognised", every=0.5)

    @pytest.mark.parametrize("value", [None, 0, -1, float("nan"), float("inf"), "invalid"])
    def test_safe_fps_uses_default_for_invalid_metadata(self, value):
        assert pose_lib._safe_fps(value) == 30.0

    def test_subject_selection_confidence_flags_competing_person_track(self):
        def track(offset):
            dets = {}
            for frame in range(12):
                x = offset + frame * 3
                kp = np.zeros((17, 2), dtype=float)
                kp[:, 0] = x + np.arange(17) * 0.1
                kp[:, 1] = 20 + np.arange(17) * 2
                dets[frame] = {
                    "box": np.array([x, 10, x + 30, 110], dtype=float),
                    "kp": kp,
                    "sc": np.ones(17, dtype=float) * 0.9,
                }
            return {"dets": dets}

        selected = track(0)
        assert pose_lib._subject_selection_confidence([selected], selected, 200)["confidence"] == "high"
        result = pose_lib._subject_selection_confidence([selected, track(80)], selected, 200)
        assert result["confidence"] == "low"
        assert result["competing_tracks"] == 1

    def test_safe_fps_preserves_valid_source_rate(self):
        assert pose_lib._safe_fps(59.94) == pytest.approx(59.94)

    def test_video_quality_screen_flags_low_light_blur_and_low_fps(self):
        dark_blurred = np.zeros((480, 640, 3), dtype=np.uint8)
        quality = pose_lib.assess_video_quality([dark_blurred], fps=15, width=640, height=480)
        assert quality["rating"] == "review"
        assert "low_frame_rate" in quality["flags"]
        assert "low_light" in quality["flags"]
        assert "possible_blur_or_motion_blur" in quality["flags"]
        assert quality["method"] == "screening_heuristics_not_calibrated"

    def test_video_quality_screen_does_not_flag_clear_well_lit_capture(self):
        yy, xx = np.indices((720, 1280))
        checker = (((xx // 8 + yy // 8) % 2) * 180 + 40).astype(np.uint8)
        frame = np.repeat(checker[:, :, None], 3, axis=2)
        quality = pose_lib.assess_video_quality([frame], fps=60, width=1280, height=720)
        assert quality["rating"] == "good"
        assert quality["flags"] == []

    def test_video_quality_screen_reports_unavailable_sampling(self):
        quality = pose_lib.assess_video_quality([], fps=30, width=1920, height=1080)
        assert quality["rating"] == "review"
        assert "quality_sampling_unavailable" in quality["flags"]

    def test_pose_metrics_reject_low_confidence_joints(self):
        p = synth_pose("right")
        front_knee = biomech.LA["knee"]
        p["frames"][0]["k"][front_knee][2] = 0.1
        p["frames"][0]["k"][biomech.RA["elbow"]][2] = 0.1

        metrics = pose_lib.metrics_at(p, 0.0, "right")
        assert metrics["front_knee"] is None
        assert metrics["bowling_elbow"] is None
        assert metrics["back_knee"] is not None

        timeline = pose_lib.timeline_text(p, "right", every=0.5)
        first = timeline.splitlines()[0]
        assert "fk=na" in first
        assert "el=na" in first

    def test_pose_metrics_reject_collapsed_joint_segments(self):
        p = synth_pose("right")
        hip, knee, ankle = biomech.LA["hip"], biomech.LA["knee"], biomech.LA["ankle"]
        p["frames"][0]["k"][hip][:2] = [0.5, 0.5]
        p["frames"][0]["k"][knee][:2] = [0.501, 0.5]
        p["frames"][0]["k"][ankle][:2] = [0.502, 0.5]
        metrics = pose_lib.metrics_at(p, 0.0, "right")
        assert metrics["front_knee"] is None

    def test_pose_metrics_reject_timestamp_far_from_observed_frame(self):
        p = synth_pose("right", fps=10)
        p["frames"] = [f for f in p["frames"] if f["t"] <= 0.5 or f["t"] >= 1.5]
        assert pose_lib.metrics_at(p, 1.0, "right") == {}

    def test_low_confidence_joint_is_not_measured(self):
        p = synth_pose("right")
        track = biomech.Track(p, "right")
        p["frames"][0]["k"][track.front["knee"]][2] = 0.1
        track = biomech.Track(p, "right")
        assert track.knee(0, track.front) is None

    def test_collapsed_limb_segments_are_not_measured_as_valid_angles(self):
        track = biomech.Track(synth_pose("right"), "right")
        side = track.front
        track.xy[0, side["hip"]] = [100.0, 100.0]
        track.xy[0, side["knee"]] = [101.0, 100.0]
        track.xy[0, side["ankle"]] = [102.0, 100.0]
        assert track.knee(0, side) is None

    def test_low_confidence_bowling_wrist_prevents_release_detection(self):
        p = synth_pose("right")
        for frame in p["frames"]:
            frame["k"][10][2] = 0.1
        assert biomech.detect_events(biomech.Track(p, "right")) == {}

    def test_empty_and_none_pose(self):
        for p in ({}, {"width": 0, "height": 0, "frames": []}, {"frames": [{"t": 0, "k": []}]}):
            tr = biomech.Track(p, "right")
            assert len(tr) == 0 and biomech.detect_events(tr) == {}
            assert biomech.measured(tr, {"release": 1.0}) == {}


class TestMergeAndSync:
    def test_merge_prefers_pose(self):
        ev = biomech.merge_events(
            {"release": 1.5, "ffc": 1.367, "bfc": 1.1,
             "event_methods": {"release": "wrist_apex_proxy"}},
            ai_steps_from({"finger_roll_release": 1.9, "ffc": 1.7}), 2.5
        )
        assert ev["release"] == 1.5 and ev["ffc"] == 1.367 and ev["measured"] == ["bfc", "ffc"]
        assert ev["sources"]["release"] == "skeleton"
        assert ev["event_methods"]["release"] == "wrist_apex_proxy"

    def test_merge_fallback_ai_when_pose_missing(self):
        ai = ai_steps_from({"finger_roll_release": 2.0, "ffc": 1.85, "bfc": 1.6, "take_off": 1.3})
        ev = biomech.merge_events({}, ai, 3.0)
        assert (ev["release"], ev["ffc"], ev["bfc"], ev["take_off"]) == (2.0, 1.85, 1.6, 1.3)
        assert ev["measured"] == [] and ev["end"] == 3.0
        assert ev["estimated"] == ["bfc", "ffc", "release", "take_off"]
        assert set(ev["sources"].values()) == {"ai"}

    def test_merge_fallback_typical_gaps_and_wrist_snap(self):
        ev = biomech.merge_events({}, ai_steps_from({"wrist_snap": 2.0, "ffc": 2.4}), 0)
        assert ev["release"] == 2.0
        assert ev["ffc"] == pytest.approx(1.87) and ev["bfc"] == pytest.approx(1.65) and ev["take_off"] == pytest.approx(1.33)
        assert ev["end"] == pytest.approx(3.5)
        assert ev["sources"] == {"release": "ai", "ffc": "template", "bfc": "template", "take_off": "template"}
        assert ev["measured"] == []

    def test_merge_rejects_out_of_clip_release(self):
        assert biomech.merge_events({}, ai_steps_from({"finger_roll_release": 4.0}), 2.5) is None

    def test_merge_rejects_out_of_clip_secondary_events(self):
        ai = ai_steps_from({"finger_roll_release": 1.5, "ffc": 2.4, "bfc": 1.2, "take_off": 0.8})
        ev = biomech.merge_events({}, ai, 2.5)
        assert ev["sources"]["release"] == "ai"
        assert ev["sources"]["ffc"] == "template"
        assert ev["ffc"] == pytest.approx(1.37)
        assert all(0 <= ev[k] <= 2.5 for k in ("release", "ffc", "bfc", "take_off"))

    def test_merge_none_when_no_release(self):
        assert biomech.merge_events({}, [], 3.0) is None
        assert biomech.merge_events({}, [{"key": "bfc", "t": None}, "junk"], 3.0) is None

    def test_merge_ignores_release_timestamp_when_step_is_not_visible(self):
        ai = ai_steps_from({"finger_roll_release": 1.5})
        ai[-4]["status"] = "not_visible"
        assert biomech.merge_events({}, ai, 2.5) is None

    def test_sync_ignores_timestamp_for_not_visible_step(self):
        ev = biomech.merge_events({}, ai_steps_from({"finger_roll_release": 1.5}), 2.5)
        ai = ai_steps_from({"run_up_acceleration": 0.3, "finger_roll_release": 1.5})
        ai[0]["status"] = "not_visible"
        times = biomech.sync_times(ai, ev)
        assert times["run_up_acceleration"] is None

    @pytest.mark.parametrize("ai_times", [{}, {k: 0.0 for k in KEYS}, {k: 9.9 for k in KEYS},
                                          {k: 2.5 - i * 0.09 for i, k in enumerate(KEYS)}])
    def test_sync_never_invents_times_outside_detected_windows(self, ai_times):
        ev = biomech.merge_events({"release": 1.5, "ffc": 1.367, "bfc": 1.1, "take_off": 0.833}, [], 2.5)
        times = biomech.sync_times(ai_steps_from(ai_times), ev)
        seq = [times[k] for k in KEYS if times[k] is not None]
        assert seq == sorted(seq), seq
        for sk, ek in EVENT_STEPS.items():
            assert times[sk] == pytest.approx(ev[ek], abs=1e-3), (sk, times[sk], ev[ek])
        assert all(0 <= t <= ev["end"] for t in seq)

    def test_sync_does_not_create_times_when_anchor_events_are_templates(self):
        ev = biomech.merge_events({}, ai_steps_from({"finger_roll_release": 1.5}), 2.5)
        times = biomech.sync_times([], ev)
        assert times["bfc"] is None and times["ffc"] is None and times["take_off"] is None
        assert times["finger_roll_release"] == pytest.approx(1.5)

    def test_sync_uses_ai_times_when_template_events_cannot_anchor_steps(self):
        ev = biomech.merge_events({}, ai_steps_from({"finger_roll_release": 1.5}), 2.5)
        ai = ai_steps_from({k: 0.2 + i * 0.05 for i, k in enumerate(KEYS)})
        times = biomech.sync_times(ai, ev)
        assert any(times[k] is not None for k in KEYS)
        assert all(times[k] is None or 0 <= times[k] <= 2.5 for k in KEYS)

    def test_release_at_end_of_clip_stays_within_duration(self):
        ev = biomech.merge_events({"release": 2.45, "ffc": 2.3, "bfc": 2.1, "take_off": 1.8}, [], 2.5)
        times = biomech.sync_times([], ev)
        assert all(t is None or 0 <= t <= 2.5 for t in times.values())
        assert times["bfc"] == pytest.approx(2.1)
        assert times["ffc"] == pytest.approx(2.3)
        assert times["take_off"] == pytest.approx(1.8)


class TestMeasured:
    def test_measured_keys_and_text(self):
        p = synth_pose("right")
        tr = biomech.Track(p, "right")
        ev = biomech.merge_events(biomech.detect_events(tr), [], 2.5)
        m = biomech.measured(tr, ev)
        print("measured", m)
        for k in ("bfc", "back_knee_compression", "posterior_trunk_tilt", "ffc", "delivery_stride"):
            assert k in m, k
        # The wrist-apex proxy is not confirmed ball release, so it must not
        # generate release-anchored measurements under a ball-release step.
        assert set(m) <= set(KEYS)
        txt = biomech.measured_text(ev, m)
        assert "BFC=" in txt and "release=" in txt
        assert "pose-derived" in txt
        assert ev["event_methods"]["release"] == "wrist_apex_proxy"
        assert ev["joint_confidence"]["release"] is not None
        assert ev["joint_confidence"]["ffc"] is not None
        assert "event_confidence" not in ev
        assert "not confirmed ball release" in txt
        assert "finger_roll_release" not in m
        assert "forward_trunk_flexion" not in m
        assert "peak_approach_velocity" not in m
        assert "arm_circumduction" not in m
        assert pose_lib.metrics_at(p, ev["release"], "right")["front_knee"] >= 0

    def test_release_metric_is_explicitly_wrist_height_not_finger_roll(self):
        track = biomech.Track(synth_pose("right"), "right")
        ev = biomech.detect_events(track)
        ev["event_methods"]["release"] = "ai_visual_estimate"
        ev["measured"] = sorted(set(ev.get("measured", [])) | {"release"})
        metrics = biomech.measured(track, ev)
        assert "finger_roll_release" in metrics
        assert "wrist_height_at_release_pct" in metrics["finger_roll_release"]
        assert "wrist_height_at_apex_pct" not in metrics["finger_roll_release"]


    @pytest.mark.parametrize("hidden_ankle", [15, 16])
    def test_release_wrist_height_survives_single_ankle_occlusion(self, hidden_ankle):
        track = biomech.Track(synth_pose("right"), "right")
        ev = biomech.detect_events(track)
        ev["event_methods"]["release"] = "ai_visual_estimate"
        ev["measured"] = sorted(set(ev.get("measured", [])) | {"release"})
        i_rel = track.idx(ev["release"])
        track.c[i_rel, hidden_ankle] = 0.0
        metrics = biomech.measured(track, ev)
        assert "wrist_height_at_release_pct" in metrics["finger_roll_release"]

    def test_release_wrist_height_uses_clip_ground_when_both_ankles_are_occluded_at_release(self):
        track = biomech.Track(synth_pose("right"), "right")
        ev = biomech.detect_events(track)
        ev["event_methods"]["release"] = "ai_visual_estimate"
        ev["measured"] = sorted(set(ev.get("measured", [])) | {"release"})
        i_rel = track.idx(ev["release"])
        track.c[i_rel, 15] = 0.0
        track.c[i_rel, 16] = 0.0
        metrics = biomech.measured(track, ev)
        assert "wrist_height_at_release_pct" in metrics["finger_roll_release"]

    def test_release_wrist_height_is_omitted_without_clip_ground_reference(self):
        pose = synth_pose("right")
        for frame in pose["frames"]:
            frame["k"][15][2] = 0.0
            frame["k"][16][2] = 0.0
        track = biomech.Track(pose, "right")
        ev = biomech.detect_events(track)
        ev["event_methods"]["release"] = "ai_visual_estimate"
        ev["measured"] = sorted(set(ev.get("measured", [])) | {"release"})
        metrics = biomech.measured(track, ev)
        assert "finger_roll_release" not in metrics

    def test_front_knee_release_angle_is_omitted_when_release_pose_is_occluded(self):
        track = biomech.Track(synth_pose("right"), "right")
        ev = biomech.detect_events(track)
        assert ev.get("ffc") is not None and ev.get("release") is not None
        ev["event_methods"]["release"] = "ai_visual_estimate"
        ev["measured"] = sorted(set(ev.get("measured", [])) | {"ffc", "release"})
        i_rel = track.idx(ev["release"])
        front = track.front
        for joint in (front["hip"], front["knee"], front["ankle"]):
            track.c[i_rel, joint] = 0.0

        metrics = biomech.measured(track, ev)

        assert "front_knee_bracing" in metrics
        assert "front_knee_ffc" in metrics["front_knee_bracing"]
        assert "knee_flex_after_ffc" in metrics["front_knee_bracing"]
        assert "front_knee_release" not in metrics["front_knee_bracing"]

    def test_zero_degree_front_arm_elevation_is_not_treated_as_missing(self):
        track = biomech.Track(synth_pose("right"), "right")
        ev = biomech.merge_events(biomech.detect_events(track), [], 2.5)
        pre = track.range(ev["ffc"] - 0.12, ev["ffc"])
        assert len(pre) > 0
        front = track.front
        for i in pre:
            shoulder = track.xy[i, front["shoulder"]].copy()
            track.xy[i, front["hip"]] = shoulder + [0.0, 30.0]
            track.xy[i, front["elbow"]] = shoulder + [0.0, 60.0]
        metrics = biomech.measured(track, ev)
        assert metrics["front_arm_elevation"]["front_arm_elevation"] == 0

    def test_stride_uses_horizontal_projection_not_airborne_foot_height(self):
        track = biomech.Track(synth_pose("right"), "right")
        ev = biomech.merge_events(biomech.detect_events(track), [], 2.5)
        i_ffc = track.idx(ev["ffc"])
        front_ankle, back_ankle = track.front["ankle"], track.arm["ankle"]
        track.xy[i_ffc, front_ankle] = [900.0, 900.0]
        track.xy[i_ffc, back_ankle] = [700.0, 500.0]

        metrics = biomech.measured(track, ev)

        expected = 200.0 / track.height_px * 100
        assert metrics["delivery_stride"]["stride_pct_height"] == round(expected)

    def test_back_knee_compression_is_omitted_with_only_one_valid_window_frame(self):
        track = biomech.Track(synth_pose("right"), "right")
        ev = biomech.merge_events(biomech.detect_events(track), [], 2.5)
        ids = track.range(ev["bfc"] + 0.02, ev["bfc"] + 0.15)
        assert len(ids) >= 2
        side = track.arm
        i_bfc = track.idx(ev["bfc"])
        for i in ids:
            if i == i_bfc:
                continue
            for joint in (side["hip"], side["knee"], side["ankle"]):
                track.c[i, joint] = 0.0

        metrics = biomech.measured(track, ev)

        assert "back_knee_compression" not in metrics

    def test_front_arm_elevation_is_omitted_with_only_one_valid_window_frame(self):
        track = biomech.Track(synth_pose("right"), "right")
        ev = biomech.merge_events(biomech.detect_events(track), [], 2.5)
        ids = track.range(ev["ffc"] - 0.12, ev["ffc"])
        assert len(ids) >= 2
        side = track.front
        for i in ids[1:]:
            for joint in (side["hip"], side["shoulder"], side["elbow"]):
                track.c[i, joint] = 0.0

        metrics = biomech.measured(track, ev)

        assert "front_arm_elevation" not in metrics

