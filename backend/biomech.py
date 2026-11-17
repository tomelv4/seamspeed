"""27-step fast-bowling model: timing windows, event detection and measured values from the tracked skeleton.

Key events (back-foot contact, front-foot contact, release) are detected from the bowler's ankles and
bowling wrist. Every step then has a time window relative to those events, so each step is shown at the
right moment of the action even when the AI's own timestamp drifts.
"""
import math

import numpy as np

# key, name, phase, when it happens, ideal
STEPS = [
    ("run_up_acceleration", "Run-Up Acceleration", "run_up",
     "At the start of the run-up as you build speed.",
     "Build speed smoothly and rhythmically. The approach should be repeatable and controlled, without stuttering or visibly decelerating."),
    ("peak_approach_velocity", "Peak Approach Velocity", "run_up",
     "Near the end of the run-up, right before the crease.",
     "Maintain a fast, balanced approach into the bound. Speed and head displacement need calibrated tracking to quantify."),
    ("pre_delivery_stride", "Pre-Delivery Stride Adjustment", "run_up",
     "On the second-to-last running step, right before the jump.",
     "Transition naturally into the bound without abrupt braking, stuttering or excessive reaching. The ideal adjustment varies by bowler."),
    ("take_off", "Take-Off (The Bound)", "load",
     "At the end of the run-up as you push off into the leap.",
     "Bound forward into the gather with controlled, balanced flight. Take-off forces and precise 3D trajectory are not measurable from this 2D view."),
    ("gather", "The Gather", "load",
     "While floating in mid-air during the bound.",
     "Coordinate the hands, front arm and body into a repeatable delivery position. Exact hand-to-chest distances vary between bowlers."),
    ("airborne_alignment", "Airborne Body Alignment", "load",
     "In mid-air as the body turns into the bowling position.",
     "Maintain stable, repeatable hip and trunk alignment. 3D rotational alignment requires calibrated multi-view capture."),
    ("posterior_trunk_tilt", "Posterior Trunk Tilt", "load",
     "At the peak of the bound, right before the back foot lands.",
     "Avoid an exaggerated backward arch. Trunk position can be described qualitatively, not judged against one universal target angle."),
    ("bfc", "Back-Foot Contact (BFC)", "back_foot",
     "The exact moment the back foot lands from the bound.",
     "Land the back foot with controlled alignment and balance. Impact force and loading time require force or calibrated 3D measurement."),
    ("back_knee_compression", "Back-Knee Compression", "back_foot",
     "The split-second after the back foot lands.",
     "Allow controlled knee flexion to absorb landing and transition forward. There is no single universal back-knee angle target."),
    ("counter_rotation", "Hip-Shoulder Counter-Rotation", "back_foot",
     "While the back foot is down and the front leg is still in the air.",
     "Avoid abrupt or excessive trunk rotation. Hip-shoulder separation cannot be reliably quantified from a single 2D camera view."),
    ("front_arm_elevation", "Front-Arm Elevation", "back_foot",
     "Just before the front foot lands.",
     "Use the front arm to organise trunk movement and balance. The most effective height and path vary between bowlers."),
    ("delivery_stride", "Delivery Stride Extension", "front_foot",
     "Right after back-foot contact as the front leg reaches forward.",
     "Reach into front-foot contact without overstriding or losing balance. Stride length relative to body height is only a rough 2D estimate."),
    ("ffc", "Front-Foot Contact (FFC)", "front_foot",
     "The exact moment the front heel lands on the pitch.",
     "Plant the front foot with stable alignment toward the intended direction. Ground-reaction forces and precise foot angle are not reliably measured here."),
    ("front_knee_bracing", "Front-Knee Bracing", "front_foot",
     "The split-second after front-foot contact, through to release.",
     "Observe front-knee motion through landing and release. A controlled support leg matters; a fully locked knee is not a universal requirement."),
    ("pelvic_rotation", "Pelvic Rotation", "front_foot",
     "Right after the front foot locks into place.",
     "Use coordinated hip movement through delivery. Pelvic angular velocity and 3D rotation require calibrated multi-view measurement."),
    ("hip_shoulder_separation", "Hip-to-Shoulder Separation", "front_foot",
     "As the hips spin forward while the chest still faces away.",
     "Coordinate pelvis and trunk rotation without forcing excessive separation. Quantification requires calibrated multi-view 3D data."),
    ("front_arm_pull_down", "Front-Arm Pull-Down", "release",
     "As the chest starts turning toward the batter.",
     "Use the front arm to support rhythm and trunk coordination. Exact angular speed and hand-to-hip distance are not measured by this system."),
    ("lateral_trunk_flexion", "Lateral Trunk Flexion", "release",
     "Just before release as the upper body leans sideways.",
     "Avoid uncontrolled lateral collapse. This movement is best assessed from a front or rear view, not a single side-on camera."),
    ("forward_trunk_flexion", "Forward Trunk Flexion", "release",
     "Right at release as the chest snaps forward.",
     "Move the trunk through release in a controlled, repeatable pattern. A 2D camera-plane estimate is not a 3D trunk measurement."),
    ("arm_circumduction", "Bowling Arm Circumduction", "release",
     "From front-foot contact until the ball is released.",
     "Maintain a repeatable bowling-arm path. A 2D full-body skeleton cannot establish arm angular speed or legal elbow extension."),
    ("shoulder_internal_rotation", "Shoulder Internal Rotation", "release",
     "A split-second before release, at the top of the arm swing.",
     "Shoulder internal-rotation speed and joint loading require high-speed, calibrated 3D measurement; they are not scored from this full-body view."),
    ("wrist_extension", "Wrist Extension (Cocking)", "release",
     "At the top of the arm swing just before release.",
     "Wrist position at cocking requires clear, close-up, high-frame-rate hand footage; it cannot be inferred from a coarse full-body skeleton."),
    ("wrist_snap", "Wrist Snap (Flexion)", "release",
     "The exact moment the hand reaches its highest point.",
     "Wrist action and speed require close-up, high-frame-rate hand tracking. They are not measurable from standard full-body pose data."),
    ("finger_roll_release", "Finger Roll & Ball Release", "release",
     "The final millisecond as the ball leaves the hand.",
     "Confirm ball separation and finger/seam action using clear ball-and-hand footage. A body skeleton cannot measure finger roll or ball spin."),
    ("arm_follow_through", "Arm Follow-Through & Deceleration", "follow_through",
     "Immediately after the ball leaves the hand.",
     "Allow the arm to decelerate naturally through a balanced finish. Joint loading and precise deceleration forces are not measurable here."),
    ("back_leg_swing", "Back-Leg Swing-Through", "follow_through",
     "Right after release as the back leg swings forward.",
     "Observe whether the rear leg follows through naturally without destabilising the bowler. Exact timing is only an estimate."),
    ("deceleration_strides", "Deceleration Strides", "follow_through",
     "At the very end as you run off the pitch.",
     "Finish under control and dissipate momentum safely. Stride count and distance require the full run-off to remain in frame and a calibrated scale."),
]

STEP_LIST_TEXT = "\n".join(f"{i + 1}. {k} - {n}. WHEN: {w} IDEAL: {d}" for i, (k, n, _, w, d) in enumerate(STEPS))

# window per step relative to events: (anchor, start offset, end offset) in seconds
WINDOWS = {
    "run_up_acceleration": ("start", 0.0, None),
    "peak_approach_velocity": ("take_off", -0.6, -0.15),
    "pre_delivery_stride": ("take_off", -0.45, -0.05),
    "take_off": ("take_off", -0.05, 0.05),
    "gather": ("take_off", 0.05, None),
    "airborne_alignment": ("take_off", 0.1, None),
    "posterior_trunk_tilt": ("bfc", -0.12, 0.0),
    "bfc": ("bfc", 0.0, 0.0),
    "back_knee_compression": ("bfc", 0.02, 0.12),
    "counter_rotation": ("bfc", 0.0, None),
    "front_arm_elevation": ("ffc", -0.12, 0.0),
    "delivery_stride": ("bfc", 0.05, None),
    "ffc": ("ffc", 0.0, 0.0),
    "front_knee_bracing": ("ffc", 0.02, None),
    "pelvic_rotation": ("ffc", 0.0, None),
    "hip_shoulder_separation": ("ffc", 0.0, None),
    "front_arm_pull_down": ("ffc", 0.03, None),
    "lateral_trunk_flexion": ("release", -0.08, 0.0),
    "forward_trunk_flexion": ("release", -0.04, 0.0),
    "arm_circumduction": ("ffc", 0.0, None),
    "shoulder_internal_rotation": ("release", -0.06, 0.0),
    "wrist_extension": ("release", -0.07, -0.01),
    "wrist_snap": ("release", 0.0, 0.0),
    "finger_roll_release": ("release", 0.0, 0.0),
    "arm_follow_through": ("release", 0.03, 0.35),
    "back_leg_swing": ("release", 0.1, 0.3),
    "deceleration_strides": ("release", 0.3, None),
}
# window ends that are "until the next event"
NEXT = {"run_up_acceleration": ("take_off", -0.6), "gather": ("bfc", -0.04), "airborne_alignment": ("bfc", -0.02),
        "counter_rotation": ("ffc", -0.02), "delivery_stride": ("ffc", -0.02), "front_knee_bracing": ("release", 0.0),
        "pelvic_rotation": ("release", -0.04), "hip_shoulder_separation": ("release", -0.03),
        "front_arm_pull_down": ("release", 0.0), "arm_circumduction": ("release", 0.0), "deceleration_strides": ("end", 0.0)}

LA = {"shoulder": 5, "elbow": 7, "wrist": 9, "hip": 11, "knee": 13, "ankle": 15}
RA = {"shoulder": 6, "elbow": 8, "wrist": 10, "hip": 12, "knee": 14, "ankle": 16}


def _ang(a, b, c, w, h):
    ax, ay = (a[0] - b[0]) * w, (a[1] - b[1]) * h
    cx, cy = (c[0] - b[0]) * w, (c[1] - b[1]) * h
    na, nc = math.hypot(ax, ay), math.hypot(cx, cy)
    if not na or not nc:
        return None
    return math.degrees(math.acos(max(-1, min(1, (ax * cx + ay * cy) / (na * nc)))))


class Track:
    """Bowler keypoints as arrays (pixel units) with helpers."""

    def __init__(self, pose, bowling_arm):
        self.w, self.h = pose.get("width") or 1, pose.get("height") or 1
        fr = [f for f in pose.get("frames", []) if f.get("k")]
        self.t = np.array([f["t"] for f in fr])
        k = np.array([f["k"] for f in fr], dtype=float) if fr else np.zeros((0, 17, 3))
        self.xy = k[..., :2] * [self.w, self.h]
        self.c = k[..., 2]
        arm_label = str(bowling_arm or "right").strip().lower()
        self.arm = RA if arm_label.startswith("r") or not arm_label.startswith("l") else LA
        self.front = LA if self.arm is RA else RA
        if len(fr):
            seg = lambda a, b: np.linalg.norm(self.xy[:, a] - self.xy[:, b], axis=1)
            sh = (self.xy[:, 5] + self.xy[:, 6]) / 2
            hp = (self.xy[:, 11] + self.xy[:, 12]) / 2
            leg = (seg(11, 13) + seg(13, 15) + seg(12, 14) + seg(14, 16)) / 2
            stand = np.linalg.norm(self.xy[:, 0] - sh, axis=1) + np.linalg.norm(sh - hp, axis=1) + leg
            height_joints = (0, 5, 6, 11, 12, 13, 14, 15, 16)
            height_xy = self.xy[:, height_joints, :]
            valid_height = (np.all(self.c[:, height_joints] >= 0.45, axis=1) &
                            np.all(np.isfinite(height_xy), axis=(1, 2)) & np.isfinite(stand))
            # A single fully visible frame is not a stable scale reference.
            self.height_px = float(np.median(stand[valid_height]) * 1.12) if int(valid_height.sum()) >= 3 else 0.0
            ankle_y = self.xy[:, [15, 16], 1]
            ankle_confident = (self.c[:, [15, 16]] >= 0.45) & np.isfinite(ankle_y)
            visible_ankle_y = ankle_y[ankle_confident]
            self.ground_y = float(np.percentile(visible_ankle_y, 90)) if len(visible_ankle_y) >= 4 else None
            valid_hips = np.where((self.c[:, 11] >= 0.45) & (self.c[:, 12] >= 0.45) &
                                  np.all(np.isfinite(self.xy[:, [11, 12], :]), axis=(1, 2)))[0]
            if len(valid_hips) >= 2:
                self.dir = 1.0 if hp[valid_hips[-1], 0] >= hp[valid_hips[0], 0] else -1.0
            else:
                self.dir = 1.0
        else:
            self.height_px = 0.0
            self.ground_y = None
            self.dir = 1.0

    def __len__(self):
        return len(self.t)

    def idx(self, t):
        return int(np.argmin(np.abs(self.t - t))) if len(self.t) else None

    def range(self, a, b):
        return np.where((self.t >= a) & (self.t <= b))[0]

    def p(self, i, j):
        return self.xy[i, j]

    def joints_confident(self, i, *joints, threshold=0.45):
        return all(
            0 <= j < self.c.shape[1]
            and np.isfinite(self.c[i, j]) and self.c[i, j] >= threshold
            and np.all(np.isfinite(self.xy[i, j]))
            for j in joints
        )

    def trunk_lean(self, i):
        """Signed trunk lean in the camera plane: + = toward the batter (direction of run), - = backward."""
        if not self.joints_confident(i, 5, 6, 11, 12):
            return None
        sh = (self.xy[i, 5] + self.xy[i, 6]) / 2
        hp = (self.xy[i, 11] + self.xy[i, 12]) / 2
        d = sh - hp
        if np.linalg.norm(d) < max(2.0, 0.05 * self.height_px) or not d[1]:
            return None
        return math.degrees(math.atan2(d[0] * self.dir, abs(d[1])))

    def _segments_visible(self, i, *pairs):
        # Very short limbs are usually collapsed/noisy keypoint estimates; their
        # angles are numerically defined but biomechanically meaningless.
        minimum = max(2.0, 0.025 * self.height_px)
        return all(np.linalg.norm(self.xy[i, a] - self.xy[i, b]) >= minimum for a, b in pairs)

    def knee(self, i, side):
        hip, knee, ankle = side["hip"], side["knee"], side["ankle"]
        if not self.joints_confident(i, hip, knee, ankle) or not self._segments_visible(i, (hip, knee), (knee, ankle)):
            return None
        return _ang(self.xy[i, hip] / [self.w, self.h], self.xy[i, knee] / [self.w, self.h],
                    self.xy[i, ankle] / [self.w, self.h], self.w, self.h)

    def joint(self, i, a, b, c):
        if not self.joints_confident(i, a, b, c) or not self._segments_visible(i, (a, b), (b, c)):
            return None
        return _ang(self.xy[i, a] / [self.w, self.h], self.xy[i, b] / [self.w, self.h], self.xy[i, c] / [self.w, self.h], self.w, self.h)


def _landing(track, ankle, a, b):
    """Estimate foot contact using a clip-wide ground reference and sustained near-ground frames."""
    if track.height_px <= 0:
        return None
    ids = track.range(a, b)
    valid_all = np.where((track.c[:, ankle] >= 0.45) & np.all(np.isfinite(track.xy[:, ankle]), axis=1))[0]
    ids = ids[(track.c[ids, ankle] >= 0.45) & np.all(np.isfinite(track.xy[ids, ankle]), axis=1)] if len(ids) else ids
    if len(ids) < 4 or len(valid_all) < 4:
        return None
    # Image y increases downward. A high percentile approximates the lowest (grounded) ankle positions.
    ground_y = float(np.percentile(track.xy[valid_all, ankle, 1], 90))
    y = track.xy[ids, ankle, 1]
    if float(np.ptp(y)) < 0.04 * track.height_px:
        return None  # no clearly visible swing-to-ground movement
    top = int(np.argmin(y))
    after = ids[top:]
    tol = 0.02 * track.height_px
    # Require three consecutive, temporally adjacent near-ground observations.
    # A single crossing (or a two-frame detector glitch) is not enough evidence
    # to call a foot contact event.
    # Use elapsed time, not just frame indices: at low source FPS, three
    # detections can span hundreds of milliseconds and are not a contact plateau.
    sample_intervals = np.diff(track.t)
    sample_intervals = sample_intervals[sample_intervals > 0]
    if not len(sample_intervals):
        return None
    max_gap_s = max(0.04, 1.6 * float(np.median(sample_intervals)))
    for pos in range(len(after) - 2):
        window = after[pos:pos + 3]
        if np.any(np.diff(track.t[window]) > max_gap_s):
            continue
        ys = track.xy[window, ankle, 1]
        if np.all(ys >= ground_y - tol) and float(np.ptp(ys)) <= 0.015 * track.height_px:
            return float(track.t[window[0]])
    return None

def detect_events(track):
    """Release, FFC, BFC and take-off times from the tracked bowler (None when not detectable)."""
    if len(track) < 8 or track.height_px <= 0:
        return {}
    arm = track.arm
    shoulders_ok = (track.c[:, 5] >= 0.45) & (track.c[:, 6] >= 0.45)
    critical_xy = track.xy[:, [5, 6, arm["wrist"]], :]
    ok = ((track.c[:, arm["wrist"]] >= 0.45) & shoulders_ok &
          np.all(np.isfinite(critical_xy), axis=(1, 2)))
    if ok.sum() < 3:
        return {}
    sh_y = (track.xy[:, 5, 1] + track.xy[:, 6, 1]) / 2
    wrist_up = (sh_y - track.xy[:, arm["wrist"], 1]) / track.height_px
    if wrist_up[ok].max() < 0.12:
        return {}
    i_rel = int(np.argmax(np.where(ok, wrist_up, -9)))
    ev = {
        "release": float(track.t[i_rel]),
        "event_methods": {"release": "wrist_apex_proxy"},
        "joint_confidence": {"release": round(float(min(track.c[i_rel, arm["wrist"]], track.c[i_rel, 5], track.c[i_rel, 6])), 2)},
    }
    ffc = _landing(track, track.front["ankle"], ev["release"] - 0.45, ev["release"] - 0.02)
    if ffc is not None:
        ev["ffc"] = ffc
        i_ffc = track.idx(ffc)
        ev["event_methods"]["ffc"] = "ankle_ground_contact_heuristic"
        ev["joint_confidence"]["ffc"] = round(float(track.c[i_ffc, track.front["ankle"]]), 2)
        bfc = _landing(track, arm["ankle"], ffc - 0.5, ffc - 0.06)
        if bfc is not None:
            ev["bfc"] = bfc
            i_bfc = track.idx(bfc)
            ev["event_methods"]["bfc"] = "ankle_ground_contact_heuristic"
            ev["joint_confidence"]["bfc"] = round(float(track.c[i_bfc, arm["ankle"]]), 2)
    return ev


def _valid_event_time(value, duration=None):
    """Return a finite, in-clip event time or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    if not math.isfinite(value) or value < 0:
        return None
    if duration is not None and value > duration:
        return None
    return value


def merge_events(pose_ev, ai_steps, duration):
    """Merge event timings while preserving whether each came from pose, AI, or a template."""
    duration = _valid_event_time(duration)
    limit = duration if duration and duration > 0 else None
    pose_ev = pose_ev if isinstance(pose_ev, dict) else {}
    ai = {}
    for step in ai_steps or []:
        if isinstance(step, dict) and step.get("status") in {"good", "ok", "fault"}:
            value = _valid_event_time(step.get("t"), limit)
            if value is not None and isinstance(step.get("key"), str):
                ai[step["key"]] = value

    ev, sources, methods, confidences = {}, {}, {}, {}
    pose_methods = pose_ev.get("event_methods", {})
    pose_confidence = pose_ev.get("joint_confidence", {})
    for key, ai_key in (("release", "finger_roll_release"), ("ffc", "ffc"),
                        ("bfc", "bfc"), ("take_off", "take_off")):
        pose_time = _valid_event_time(pose_ev.get(key), limit)
        ai_time = ai.get(ai_key)
        if pose_time is not None:
            ev[key], sources[key] = pose_time, "skeleton"
            methods[key] = pose_methods.get(key, "pose_heuristic")
            confidences[key] = float(pose_confidence.get(key, 0.0))
        elif ai_time is not None:
            ev[key], sources[key] = ai_time, "ai"
            methods[key], confidences[key] = "ai_visual_estimate", None
        else:
            ev[key], sources[key] = None, None
            methods[key], confidences[key] = "unavailable", None

    if ev["release"] is None and ai.get("wrist_snap") is not None:
        ev["release"], sources["release"] = ai["wrist_snap"], "ai"
        methods["release"], confidences["release"] = "ai_visual_estimate", None
    if ev["release"] is None:
        return None

    if ev["ffc"] is None or not (ev["release"] - 0.5 < ev["ffc"] < ev["release"]):
        ev["ffc"], sources["ffc"] = max(0.0, ev["release"] - 0.13), "template"
        methods["ffc"], confidences["ffc"] = "typical_gap_estimate", None
    if ev["bfc"] is None or not (ev["ffc"] - 0.6 < ev["bfc"] < ev["ffc"]):
        ev["bfc"], sources["bfc"] = max(0.0, ev["ffc"] - 0.22), "template"
        methods["bfc"], confidences["bfc"] = "typical_gap_estimate", None
    if ev["take_off"] is None or not (ev["bfc"] - 0.8 < ev["take_off"] < ev["bfc"]):
        ev["take_off"], sources["take_off"] = max(0.0, ev["bfc"] - 0.32), "template"
        methods["take_off"], confidences["take_off"] = "typical_gap_estimate", None

    ev["start"] = 0.0
    ev["end"] = limit if limit is not None else max(float(duration or 0), ev["release"] + 1.5)
    ev["sources"] = sources
    ev["event_methods"] = methods
    ev["joint_confidence"] = confidences
    # A wrist-height apex is a pose-derived proxy, not a detected ball-release event.
    # Keep its provenance in event_methods, but do not count it as a measured event.
    ev["pose_detected"] = sorted(
        k for k, source in sources.items()
        if source == "skeleton" and not (k == "release" and methods.get(k) == "wrist_apex_proxy")
    )
    ev["measured"] = ev["pose_detected"]  # legacy alias for older report consumers
    ev["estimated"] = sorted(k for k, source in sources.items() if source != "skeleton")
    return ev


def step_window(key, ev):
    anchor, a, b = WINDOWS[key]
    start = ev[anchor] + a
    if b is None:
        nk, off = NEXT[key]
        end = ev[nk] + off
    else:
        end = ev[anchor] + b
    start, end = max(ev["start"], start), min(ev["end"], end)
    start = min(start, ev["end"])
    return start, max(start, end)


def sync_times(ai_steps, ev):
    """Use event windows only when their anchors are genuinely detected; never invent missing step times."""
    by_key = {
        s.get("key"): s for s in (ai_steps or [])
        if isinstance(s, dict) and s.get("status") in {"good", "ok", "fault"} and isinstance(s.get("key"), str)
    }
    sources = ev.get("sources", {})
    methods = ev.get("event_methods", {})
    out, last = {}, 0.0

    def anchor_is_usable(anchor):
        source = sources.get(anchor)
        method = methods.get(anchor)
        return source in ("skeleton", "ai") and method not in (None, "wrist_apex_proxy", "typical_gap_estimate", "unavailable")

    for key, *_ in STEPS:
        anchor, _, _ = WINDOWS[key]
        required = [anchor]
        if WINDOWS[key][2] is None and key in NEXT:
            required.append(NEXT[key][0])
        usable_window = all(a == "start" or a == "end" or anchor_is_usable(a) for a in required)

        raw = by_key.get(key, {}).get("t")
        t = _valid_event_time(raw, ev.get("end"))
        if usable_window:
            a, b = step_window(key, ev)
            if key in ("bfc", "ffc", "take_off") and sources.get(key) in ("skeleton", "ai"):
                t = ev[key]
            elif t is not None and a <= t <= b:
                pass
            elif key == "finger_roll_release" and sources.get("release") == "ai":
                t = ev["release"]
            else:
                t = None
        elif key == "finger_roll_release" and sources.get("release") == "ai":
            t = ev["release"]
        if t is not None:
            t = float(t)
            if t < last:
                t = None
            else:
                last = t
        out[key] = round(t, 3) if t is not None else None
    return out

def _window_values(track, ids, measure, min_samples=2):
    """Return window measurements only when observations provide continuous temporal support."""
    values = []
    for i in ids:
        value = measure(int(i))
        if value is not None:
            values.append((float(track.t[i]), value))
    values.sort(key=lambda item: item[0])
    times = [t for t, _ in values]
    if len(values) < min_samples or len(set(times)) < min_samples:
        return []
    intervals = np.diff(track.t)
    intervals = intervals[intervals > 0]
    if len(intervals):
        max_gap = max(0.06, 1.6 * float(np.median(intervals)))
        if any(gap > max_gap for gap in np.diff(times)):
            return []
    return [value for _, value in values]


def measured(track, ev):
    """Measured values per step (2D estimates from the side camera) used for judging against the ideals."""
    if not len(track) or not ev:
        return {}
    arm, front = track.arm, track.front
    H = track.height_px
    m = {}
    intervals = np.diff(track.t)
    intervals = intervals[intervals > 0]
    sample_tolerance = min(0.12, max(0.025, 0.75 * float(np.median(intervals)))) if len(intervals) else 0.025

    def at(t):
        if t is None:
            return None
        i = track.idx(t)
        return i if i is not None and abs(float(track.t[i]) - float(t)) <= sample_tolerance else None

    # Pose-derived and AI-timed events can both anchor a 2D skeleton measurement:
    # the joint positions come from pose tracking, while the event source remains
    # separately visible in the report. Template times and wrist-apex proxies
    # must never be treated as measured biomechanical events.
    usable = set(ev.get("pose_detected", ev.get("measured", [])))
    sources = ev.get("sources", {})
    methods = ev.get("event_methods", {})
    for key in ("bfc", "ffc", "release"):
        if sources.get(key) in ("skeleton", "ai") and methods.get(key) not in (
            None, "wrist_apex_proxy", "typical_gap_estimate", "unavailable"
        ):
            usable.add(key)
    if methods.get("release") == "wrist_apex_proxy":
        usable.discard("release")
    i_bfc, i_ffc, i_rel = [at(ev.get(k)) if k in usable else None for k in ("bfc", "ffc", "release")]
    if i_bfc is not None:
        bk = track.knee(i_bfc, arm)
        if bk is not None:
            m.setdefault("bfc", {})["back_knee"] = round(bk)
        ids = track.range(ev["bfc"], ev["bfc"] + 0.15)
        vals = _window_values(track, ids, lambda i: track.knee(i, arm))
        if vals:
            m["back_knee_compression"] = {"back_knee_min": round(min(vals))}
            if bk is not None:
                m["back_knee_compression"]["knee_flex_after_bfc"] = round(max(0, bk - min(vals)))
        pre = track.range(ev["bfc"] - 0.12, ev["bfc"])
        if len(pre):
            leans = _window_values(track, pre, track.trunk_lean)
            if leans:
                m["posterior_trunk_tilt"] = {"backward_lean_2d_est": round(max(0, -min(leans)))}
    if i_ffc is not None:
        fk = track.knee(i_ffc, front)
        stride = None
        if track.joints_confident(i_ffc, front["ankle"], arm["ankle"]) and H > 0:
            # Side-on stride extension is the projected horizontal separation.
            # Euclidean foot-to-foot distance inflates the result when the rear
            # foot is airborne at front-foot contact.
            stride = abs(track.p(i_ffc, front["ankle"])[0] - track.p(i_ffc, arm["ankle"])[0]) / H * 100
        ffc_values = {}
        if fk is not None:
            ffc_values["front_knee"] = round(fk)
        if stride is not None:
            ffc_values["stride_pct_height"] = round(stride)
            m["delivery_stride"] = {"stride_pct_height": round(stride)}
        if ffc_values:
            m["ffc"] = ffc_values
        if i_rel is not None and i_rel >= i_ffc and fk is not None:
            knee_ids = range(i_ffc, i_rel + 1)
            vals = _window_values(track, knee_ids, lambda i: track.knee(i, front))
            if vals:
                bracing = {
                    "front_knee_ffc": round(fk),
                    "knee_flex_after_ffc": round(max(0, fk - min(vals))),
                }
                # Only label an angle as the release value when the knee is
                # actually visible and measurable in the release frame.
                release_knee = track.knee(i_rel, front)
                if release_knee is not None:
                    bracing["front_knee_release"] = round(release_knee)
                m["front_knee_bracing"] = bracing
        pre = track.range(ev["ffc"] - 0.12, ev["ffc"])
        if len(pre):
            el = _window_values(track, pre, lambda i: track.joint(i, front["hip"], front["shoulder"], front["elbow"]))
            if el:
                m["front_arm_elevation"] = {"front_arm_elevation": round(max(el))}
    if i_rel is not None and H > 0 and track.ground_y is not None and track.joints_confident(i_rel, arm["wrist"]):
        # Use a clip-wide ankle-ground reference. The feet may both be airborne
        # at release, so their instantaneous positions are not a ground plane.
        rel_h = (track.ground_y - track.xy[i_rel, arm["wrist"], 1]) / H * 100
        # A wrist below the estimated ground plane is a tracking/cropping error,
        # not a meaningful negative release height.
        if math.isfinite(rel_h) and rel_h >= 0:
            m["finger_roll_release"] = {"wrist_height_at_release_pct": round(rel_h)}
        post = track.range(ev["release"], ev["release"] + 0.15)
        leans = _window_values(track, post, track.trunk_lean)
        if leans:
            m["forward_trunk_flexion"] = {"forward_lean_max_2d_est": round(max(0, max(leans)))}
    # A single 2D view cannot establish elbow-extension legality or calibrated bowling speed.
    return m


def measured_text(ev, meas):
    source_labels = {"skeleton": "pose-derived", "ai": "AI-estimated", "template": "typical-gap estimate"}
    sources = ev.get("sources", {})
    methods = ev.get("event_methods", {})
    confidence = ev.get("joint_confidence", {})
    method_labels = {
        "wrist_apex_proxy": "wrist-apex proxy (not confirmed ball release)",
        "ankle_ground_contact_heuristic": "ankle-ground contact heuristic",
        "ankle_ground_departure_heuristic": "ankle-ground departure heuristic",
        "ai_visual_estimate": "AI visual estimate",
        "typical_gap_estimate": "typical-gap estimate",
    }
    source_text = ", ".join(
        f"{key}={source_labels.get(sources.get(key), 'unavailable')} / "
        f"{method_labels.get(methods.get(key), methods.get(key, 'unavailable'))} "
        f"(keypoint confidence {confidence[key]:.2f})" if isinstance(confidence.get(key), (int, float)) else "(keypoint confidence unavailable)"
        for key in ("take_off", "bfc", "ffc", "release")
    )
    lines = [f"Event timings (s): take_off={ev['take_off']:.2f}, BFC={ev['bfc']:.2f}, FFC={ev['ffc']:.2f}, release={ev['release']:.2f}"
             f" (pose-derived events: {', '.join(ev.get('pose_detected', ev.get('measured', []))) or 'none'}; sources: {source_text})"]
    if not ev.get("measured"):
        lines.append("No key events were detected from pose tracking. Treat all event timings as estimates, not measured evidence.")
    lines.append(f"BFC->FFC {ev['ffc'] - ev['bfc']:.2f}s, FFC->release {ev['release'] - ev['ffc']:.2f}s")
    for key, vals in meas.items():
        lines.append(f"{key}: " + ", ".join(f"{k}={v}" for k, v in vals.items()))
    return "\n".join(lines)
