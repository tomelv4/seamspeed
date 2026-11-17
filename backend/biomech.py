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
     "Accelerate smoothly over 15-25 m (10-15 strides), torso upright (0-5° forward lean), arms swinging straight within 5° of the target line."),
    ("peak_approach_velocity", "Peak Approach Velocity", "run_up",
     "Near the end of the run-up, right before the crease.",
     "Reach 5.5-7.0 m/s (80-90% of top sprint speed) with vertical head bounce under 5 cm."),
    ("pre_delivery_stride", "Pre-Delivery Stride Adjustment", "run_up",
     "On the second-to-last running step, right before the jump.",
     "Shorten this stride by 10-15% (15-25 cm shorter than a normal running stride) to lower the hips and gather energy."),
    ("take_off", "Take-Off (The Bound)", "load",
     "At the end of the run-up as you push off into the leap.",
     "Launch forward at a low 10-15° take-off angle, bound distance 1.2-1.6 m, vertical lift under 20-30 cm."),
    ("gather", "The Gather", "load",
     "While floating in mid-air during the bound.",
     "Both hands within 10-15 cm of the chest or chin, elbows tucked within 20-30 cm of the ribs."),
    ("airborne_alignment", "Airborne Body Alignment", "load",
     "In mid-air as the body turns into the bowling position.",
     "Hip and shoulder angles within 10° of each other: ~180° side-on, 200-225° semi-open or 230-250° front-on."),
    ("posterior_trunk_tilt", "Posterior Trunk Tilt", "load",
     "At the peak of the bound, right before the back foot lands.",
     "Upper body leaning 10-15° backward away from the batter for a longer whip."),
    ("bfc", "Back-Foot Contact (BFC)", "back_foot",
     "The exact moment the back foot lands from the bound.",
     "Stable landing with the foot aligned to the hips (0-45° to the crease), absorbing 2-3x body weight over 0.12-0.18 s."),
    ("back_knee_compression", "Back-Knee Compression", "back_foot",
     "The split-second after the back foot lands.",
     "Back knee bends from ~165° to 140-155° (180° = straight) to absorb impact and spring forward."),
    ("counter_rotation", "Hip-Shoulder Counter-Rotation", "back_foot",
     "While the back foot is down and the front leg is still in the air.",
     "Extra backward shoulder twist against the hips under 20° (strictly below 30°) to keep the spine safe."),
    ("front_arm_elevation", "Front-Arm Elevation", "back_foot",
     "Just before the front foot lands.",
     "Front upper arm raised to 120-140°, elbow or hand pointing within 5-10° of the target line."),
    ("delivery_stride", "Delivery Stride Extension", "front_foot",
     "Right after back-foot contact as the front leg reaches forward.",
     "Stride 75-85% of standing height (~1.35-1.65 m) while the bowling arm drops to a 180° down-and-back position."),
    ("ffc", "Front-Foot Contact (FFC)", "front_foot",
     "The exact moment the front heel lands on the pitch.",
     "Front foot pointing straight down the pitch (0-15° of the target), handling 5-9x body weight in under 0.05 s."),
    ("front_knee_bracing", "Front-Knee Bracing", "front_foot",
     "The split-second after front-foot contact, through to release.",
     "Front knee braced at 165-180° with less than 10° of bend after landing, from impact to release."),
    ("pelvic_rotation", "Pelvic Rotation", "front_foot",
     "Right after the front foot locks into place.",
     "Back hip drives forward at 400-600°/s until the hips face the batter squarely (0-10°)."),
    ("hip_shoulder_separation", "Hip-to-Shoulder Separation", "front_foot",
     "As the hips spin forward while the chest still faces away.",
     "A 30-45° rotational gap between open hips and delayed shoulders."),
    ("front_arm_pull_down", "Front-Arm Pull-Down", "release",
     "As the chest starts turning toward the batter.",
     "Front elbow pulled down at 600-900°/s and tucked within 10 cm of the front hip."),
    ("lateral_trunk_flexion", "Lateral Trunk Flexion", "release",
     "Just before release as the upper body leans sideways.",
     "Torso tilted 20-35° sideways away from the bowling arm so the hand reaches its highest point."),
    ("forward_trunk_flexion", "Forward Trunk Flexion", "release",
     "Right at release as the chest snaps forward.",
     "Chest snaps 35-50° forward and down over a straight front leg at 300-500°/s."),
    ("arm_circumduction", "Bowling Arm Circumduction", "release",
     "From front-foot contact until the ball is released.",
     "Vertical arm arc at 1,200-1,600°/s with elbow extension strictly under the legal 15° (typically 5-12°)."),
    ("shoulder_internal_rotation", "Shoulder Internal Rotation", "release",
     "A split-second before release, at the top of the arm swing.",
     "Upper arm rotates inward at 1,500-2,200°/s right before letting go."),
    ("wrist_extension", "Wrist Extension (Cocking)", "release",
     "At the top of the arm swing just before release.",
     "Wrist cocked back 20-30° behind the ball to load the forearm."),
    ("wrist_snap", "Wrist Snap (Flexion)", "release",
     "The exact moment the hand reaches its highest point.",
     "Wrist snaps forward at 1,000-1,500°/s from 20-30° extension through neutral into 10-20° flexion."),
    ("finger_roll_release", "Finger Roll & Ball Release", "release",
     "The final millisecond as the ball leaves the hand.",
     "Release at 105-115% of standing height, fingers rolling down the seam for 1,200-1,800 rpm backspin."),
    ("arm_follow_through", "Arm Follow-Through & Deceleration", "follow_through",
     "Immediately after the ball leaves the hand.",
     "Bowling arm swings freely through a 180-220° downward arc past the opposite hip, slowing over 0.25-0.35 s."),
    ("back_leg_swing", "Back-Leg Swing-Through", "follow_through",
     "Right after release as the back leg swings forward.",
     "Back knee drives past the front leg within 0.15-0.25 s of release so the hips keep moving down the pitch."),
    ("deceleration_strides", "Deceleration Strides", "follow_through",
     "At the very end as you run off the pitch.",
     "3-5 balanced steps over 6-10 m along a gentle 15-25° curve off the pitch."),
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
            valid_height = np.all(self.c[:, height_joints] >= 0.45, axis=1)
            self.height_px = float(np.median(stand[valid_height]) * 1.12) if valid_height.any() else 1.0
            valid_hips = np.where((self.c[:, 11] >= 0.45) & (self.c[:, 12] >= 0.45))[0]
            if len(valid_hips) >= 2:
                self.dir = 1.0 if hp[valid_hips[-1], 0] >= hp[valid_hips[0], 0] else -1.0
            else:
                self.dir = 1.0
        else:
            self.height_px = 1.0
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
        return all(0 <= j < self.c.shape[1] and self.c[i, j] >= threshold for j in joints)

    def trunk_lean(self, i):
        """Signed trunk lean in the camera plane: + = toward the batter (direction of run), - = backward."""
        if not self.joints_confident(i, 5, 6, 11, 12):
            return None
        sh = (self.xy[i, 5] + self.xy[i, 6]) / 2
        hp = (self.xy[i, 11] + self.xy[i, 12]) / 2
        d = sh - hp
        return math.degrees(math.atan2(d[0] * self.dir, abs(d[1]))) if d[1] else None

    def knee(self, i, side):
        joints = (side["hip"], side["knee"], side["ankle"])
        if not self.joints_confident(i, *joints):
            return None
        return _ang(self.xy[i, side["hip"]] / [self.w, self.h], self.xy[i, side["knee"]] / [self.w, self.h],
                    self.xy[i, side["ankle"]] / [self.w, self.h], self.w, self.h)

    def joint(self, i, a, b, c):
        if not self.joints_confident(i, a, b, c):
            return None
        return _ang(self.xy[i, a] / [self.w, self.h], self.xy[i, b] / [self.w, self.h], self.xy[i, c] / [self.w, self.h], self.w, self.h)


def _landing(track, ankle, a, b):
    """Estimate foot contact using a clip-wide ground reference and sustained near-ground frames."""
    ids = track.range(a, b)
    valid_all = np.where(track.c[:, ankle] >= 0.45)[0]
    ids = ids[track.c[ids, ankle] >= 0.45] if len(ids) else ids
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
    for pos in range(len(after) - 1):
        i, nxt = after[pos], after[pos + 1]
        if nxt - i > 2:
            continue
        yi = track.xy[i, ankle, 1]
        yn = track.xy[nxt, ankle, 1]
        if yi >= ground_y - tol and yn >= ground_y - tol:
            # Reject a single noisy frame that only crosses the estimated ground line.
            return float(track.t[i])
    return None

def detect_events(track):
    """Release, FFC, BFC and take-off times from the tracked bowler (None when not detectable)."""
    if len(track) < 8:
        return {}
    arm = track.arm
    shoulders_ok = (track.c[:, 5] >= 0.45) & (track.c[:, 6] >= 0.45)
    ok = (track.c[:, arm["wrist"]] >= 0.45) & shoulders_ok
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
        "event_confidence": {"release": round(float(min(track.c[i_rel, arm["wrist"]], track.c[i_rel, 5], track.c[i_rel, 6])), 2)},
    }
    ffc = _landing(track, track.front["ankle"], ev["release"] - 0.45, ev["release"] - 0.02)
    if ffc is not None:
        ev["ffc"] = ffc
        i_ffc = track.idx(ffc)
        ev["event_methods"]["ffc"] = "ankle_ground_contact_heuristic"
        ev["event_confidence"]["ffc"] = round(float(track.c[i_ffc, track.front["ankle"]]), 2)
        bfc = _landing(track, arm["ankle"], ffc - 0.5, ffc - 0.06)
        if bfc is not None:
            ev["bfc"] = bfc
            i_bfc = track.idx(bfc)
            ev["event_methods"]["bfc"] = "ankle_ground_contact_heuristic"
            ev["event_confidence"]["bfc"] = round(float(track.c[i_bfc, arm["ankle"]]), 2)
            # take-off: last moment the take-off (front-side) foot is on the ground before the bound
            ids = track.range(bfc - 0.7, bfc - 0.1)
            if len(ids) >= 3:
                y = track.xy[ids, track.front["ankle"], 1]
                ground = y.max()
                on = [i for i, v in zip(ids, y) if v >= ground - 0.03 * track.height_px]
                if on:
                    take_idx = on[-1]
                    ev["take_off"] = float(track.t[take_idx])
                    ev["event_methods"]["take_off"] = "ankle_ground_departure_heuristic"
                    ev["event_confidence"]["take_off"] = round(float(track.c[take_idx, track.front["ankle"]]), 2)
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
        if isinstance(step, dict):
            value = _valid_event_time(step.get("t"), limit)
            if value is not None:
                ai[step.get("key")] = value

    ev, sources, methods, confidences = {}, {}, {}, {}
    pose_methods = pose_ev.get("event_methods", {})
    pose_confidence = pose_ev.get("event_confidence", {})
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
            methods[key], confidences[key] = "ai_visual_estimate", 0.35
        else:
            ev[key], sources[key] = None, None
            methods[key], confidences[key] = "unavailable", 0.0

    if ev["release"] is None and ai.get("wrist_snap") is not None:
        ev["release"], sources["release"] = ai["wrist_snap"], "ai"
        methods["release"], confidences["release"] = "ai_visual_estimate", 0.35
    if ev["release"] is None:
        return None

    if ev["ffc"] is None or not (ev["release"] - 0.5 < ev["ffc"] < ev["release"]):
        ev["ffc"], sources["ffc"] = max(0.0, ev["release"] - 0.13), "template"
        methods["ffc"], confidences["ffc"] = "typical_gap_estimate", 0.0
    if ev["bfc"] is None or not (ev["ffc"] - 0.6 < ev["bfc"] < ev["ffc"]):
        ev["bfc"], sources["bfc"] = max(0.0, ev["ffc"] - 0.22), "template"
        methods["bfc"], confidences["bfc"] = "typical_gap_estimate", 0.0
    if ev["take_off"] is None or not (ev["bfc"] - 0.8 < ev["take_off"] < ev["bfc"]):
        ev["take_off"], sources["take_off"] = max(0.0, ev["bfc"] - 0.32), "template"
        methods["take_off"], confidences["take_off"] = "typical_gap_estimate", 0.0

    ev["start"] = 0.0
    ev["end"] = limit if limit is not None else max(float(duration or 0), ev["release"] + 1.5)
    ev["sources"] = sources
    ev["event_methods"] = methods
    ev["event_confidence"] = confidences
    ev["measured"] = sorted(k for k, source in sources.items() if source == "skeleton")
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
    by_key = {s.get("key"): s for s in (ai_steps or []) if isinstance(s, dict)}
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
            if key in ("bfc", "ffc", "take_off") and sources.get(key) == "skeleton":
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

def measured(track, ev):
    """Measured values per step (2D estimates from the side camera) used for judging against the ideals."""
    if not len(track) or not ev:
        return {}
    arm, front = track.arm, track.front
    H = track.height_px
    m = {}
    at = lambda t: track.idx(t) if t is not None and abs(track.t[track.idx(t)] - t) < 0.12 else None

    real = set(ev.get("measured", []))  # only judge from events actually measured on the skeleton
    i_bfc, i_ffc, i_rel = [at(ev.get(k)) if k in real else None for k in ("bfc", "ffc", "release")]
    if i_bfc is not None:
        bk = track.knee(i_bfc, arm)
        if bk:
            m.setdefault("bfc", {})["back_knee"] = round(bk)
        ids = track.range(ev["bfc"], ev["bfc"] + 0.15)
        vals = [track.knee(i, arm) for i in ids]
        vals = [v for v in vals if v]
        if vals:
            m["back_knee_compression"] = {"back_knee_min": round(min(vals))}
            if bk:
                m["back_knee_compression"]["knee_flex_after_bfc"] = round(max(0, bk - min(vals)))
        pre = track.range(ev["bfc"] - 0.12, ev["bfc"])
        if len(pre):
            leans = [track.trunk_lean(i) for i in pre]
            leans = [v for v in leans if v is not None]
            if leans:
                m["posterior_trunk_tilt"] = {"backward_lean_2d_est": round(max(0, -min(leans)))}
    if i_ffc is not None:
        fk = track.knee(i_ffc, front)
        stride = None
        if track.joints_confident(i_ffc, front["ankle"], arm["ankle"]) and H > 0:
            stride = np.linalg.norm(track.p(i_ffc, front["ankle"]) - track.p(i_ffc, arm["ankle"])) / H * 100
        ffc_values = {}
        if fk is not None:
            ffc_values["front_knee"] = round(fk)
        if stride is not None:
            ffc_values["stride_pct_height"] = round(stride)
            m["delivery_stride"] = {"stride_pct_height": round(stride)}
        if ffc_values:
            m["ffc"] = ffc_values
        if i_rel is not None and i_rel >= i_ffc:
            vals = [track.knee(i, front) for i in range(i_ffc, i_rel + 1)]
            vals = [v for v in vals if v]
            if vals and fk:
                m["front_knee_bracing"] = {"front_knee_ffc": round(fk), "front_knee_release": round(vals[-1]),
                                           "knee_flex_after_ffc": round(max(0, fk - min(vals)))}
        pre = track.range(ev["ffc"] - 0.12, ev["ffc"])
        if len(pre):
            el = [track.joint(i, front["hip"], front["shoulder"], front["elbow"]) for i in pre]
            el = [v for v in el if v]
            if el:
                m["front_arm_elevation"] = {"front_arm_elevation": round(max(el))}
    if i_rel is not None and track.joints_confident(i_rel, arm["wrist"], 15, 16):
        ground = max(track.xy[i_rel, 15, 1], track.xy[i_rel, 16, 1])
        rel_h = (ground - track.xy[i_rel, arm["wrist"], 1]) / H * 100
        m["finger_roll_release"] = {"wrist_height_at_apex_pct": round(rel_h)}
        post = track.range(ev["release"], ev["release"] + 0.15)
        leans = [track.trunk_lean(i) for i in post]
        leans = [v for v in leans if v is not None]
        if leans:
            m["forward_trunk_flexion"] = {"forward_lean_max_2d_est": round(max(0, max(leans)))}
    # A single 2D view cannot establish elbow-extension legality or calibrated bowling speed.
    return m


def measured_text(ev, meas):
    source_labels = {"skeleton": "skeleton-detected", "ai": "AI-estimated", "template": "typical-gap estimate"}
    sources = ev.get("sources", {})
    methods = ev.get("event_methods", {})
    confidence = ev.get("event_confidence", {})
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
        f"(keypoint confidence {confidence.get(key, 0):.2f})"
        for key in ("take_off", "bfc", "ffc", "release")
    )
    lines = [f"Event timings (s): take_off={ev['take_off']:.2f}, BFC={ev['bfc']:.2f}, FFC={ev['ffc']:.2f}, release={ev['release']:.2f}"
             f" (measured from skeleton: {', '.join(ev.get('measured', [])) or 'none'}; sources: {source_text})"]
    if not ev.get("measured"):
        lines.append("No key events were detected from the skeleton. Treat all event timings as estimates, not measured evidence.")
    lines.append(f"BFC->FFC {ev['ffc'] - ev['bfc']:.2f}s, FFC->release {ev['release'] - ev['ffc']:.2f}s")
    for key, vals in meas.items():
        lines.append(f"{key}: " + ", ".join(f"{k}={v}" for k, v in vals.items()))
    return "\n".join(lines)
