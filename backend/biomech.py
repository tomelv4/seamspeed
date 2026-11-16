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
        self.arm = RA if bowling_arm.lower().startswith("r") else LA
        self.front = LA if self.arm is RA else RA
        if len(fr):
            seg = lambda a, b: np.linalg.norm(self.xy[:, a] - self.xy[:, b], axis=1)
            sh = (self.xy[:, 5] + self.xy[:, 6]) / 2
            hp = (self.xy[:, 11] + self.xy[:, 12]) / 2
            leg = (seg(11, 13) + seg(13, 15) + seg(12, 14) + seg(14, 16)) / 2
            stand = np.linalg.norm(self.xy[:, 0] - sh, axis=1) + np.linalg.norm(sh - hp, axis=1) + leg
            self.height_px = float(np.median(stand) * 1.12)  # nose->ankle chain + head top / foot
            self.dir = 1.0 if hp[-1, 0] >= hp[0, 0] else -1.0  # running direction across the frame
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

    def trunk_lean(self, i):
        """Signed trunk lean in the camera plane: + = toward the batter (direction of run), - = backward."""
        sh = (self.xy[i, 5] + self.xy[i, 6]) / 2
        hp = (self.xy[i, 11] + self.xy[i, 12]) / 2
        d = sh - hp
        return math.degrees(math.atan2(d[0] * self.dir, abs(d[1]))) if d[1] else 0.0

    def knee(self, i, side):
        return _ang(self.xy[i, side["hip"]] / [self.w, self.h], self.xy[i, side["knee"]] / [self.w, self.h],
                    self.xy[i, side["ankle"]] / [self.w, self.h], self.w, self.h)

    def joint(self, i, a, b, c):
        return _ang(self.xy[i, a] / [self.w, self.h], self.xy[i, b] / [self.w, self.h], self.xy[i, c] / [self.w, self.h], self.w, self.h)


def _landing(track, ankle, a, b):
    """First frame after the foot's highest swing point where it reaches the ground level of the window."""
    ids = track.range(a, b)
    ids = ids[track.c[ids, ankle] > 0.3] if len(ids) else ids
    if len(ids) < 3:
        return None
    y = track.xy[ids, ankle, 1]
    top = int(np.argmin(y))
    after = ids[top:]
    if len(after) < 2:
        return None
    ya = track.xy[after, ankle, 1]
    ground = ya.max()
    tol = 0.025 * track.height_px
    for i, v in zip(after, ya):
        if v >= ground - tol:
            return float(track.t[i])
    return None


def detect_events(track):
    """Release, FFC, BFC and take-off times from the tracked bowler (None when not detectable)."""
    if len(track) < 8:
        return {}
    arm = track.arm
    sh_y = (track.xy[:, 5, 1] + track.xy[:, 6, 1]) / 2
    wrist_up = (sh_y - track.xy[:, arm["wrist"], 1]) / track.height_px
    ok = track.c[:, arm["wrist"]] > 0.3
    if not ok.any() or wrist_up[ok].max() < 0.12:
        return {}
    i_rel = int(np.argmax(np.where(ok, wrist_up, -9)))
    ev = {"release": float(track.t[i_rel])}
    ffc = _landing(track, track.front["ankle"], ev["release"] - 0.45, ev["release"] - 0.02)
    if ffc is not None:
        ev["ffc"] = ffc
        bfc = _landing(track, arm["ankle"], ffc - 0.5, ffc - 0.06)
        if bfc is not None:
            ev["bfc"] = bfc
            # take-off: last moment the take-off (front-side) foot is on the ground before the bound
            ids = track.range(bfc - 0.7, bfc - 0.1)
            if len(ids) >= 3:
                y = track.xy[ids, track.front["ankle"], 1]
                ground = y.max()
                on = [i for i, v in zip(ids, y) if v >= ground - 0.03 * track.height_px]
                if on:
                    ev["take_off"] = float(track.t[on[-1]])
    return ev


def merge_events(pose_ev, ai_steps, duration):
    """Prefer measured events; fall back to the AI's timestamps, then to typical gaps."""
    ai = {s.get("key"): s.get("t") for s in ai_steps if isinstance(s, dict) and isinstance(s.get("t"), (int, float))}
    ev = {}
    for k, ai_key in (("release", "finger_roll_release"), ("ffc", "ffc"), ("bfc", "bfc"), ("take_off", "take_off")):
        ev[k] = pose_ev.get(k) if pose_ev.get(k) is not None else ai.get(ai_key)
    if ev["release"] is None:
        ev["release"] = ai.get("wrist_snap")
    if ev["release"] is None:
        return None
    if ev["ffc"] is None or not (ev["release"] - 0.5 < ev["ffc"] < ev["release"]):
        ev["ffc"] = ev["release"] - 0.13
    if ev["bfc"] is None or not (ev["ffc"] - 0.6 < ev["bfc"] < ev["ffc"]):
        ev["bfc"] = ev["ffc"] - 0.22
    if ev["take_off"] is None or not (ev["bfc"] - 0.8 < ev["take_off"] < ev["bfc"]):
        ev["take_off"] = ev["bfc"] - 0.32
    ev["start"], ev["end"] = 0.0, float(duration or ev["release"] + 1.5)
    ev["measured"] = sorted(k for k in ("release", "ffc", "bfc", "take_off") if pose_ev.get(k) is not None)
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
    """Snap each step's time into its biomechanical window; keep order where the windows allow it."""
    by_key = {s.get("key"): s for s in ai_steps if isinstance(s, dict)}
    out, last = {}, 0.0
    for key, *_ in STEPS:
        a, b = step_window(key, ev)
        t = by_key.get(key, {}).get("t")
        if not isinstance(t, (int, float)) or not (a <= t <= b):
            t = (a + b) / 2 if b - a < 0.4 else (a if key in ("run_up_acceleration",) else b - min(0.15, (b - a) / 2))
            if key in ("bfc", "ffc", "wrist_snap", "finger_roll_release", "take_off"):
                t = min(ev[WINDOWS[key][0]], ev["end"])
        t = min(max(t, last), b)  # never pushed out of its own window
        out[key] = round(float(t), 3)
        last = max(last, t)
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
            m["posterior_trunk_tilt"] = {"backward_lean": round(max(0, -min(track.trunk_lean(i) for i in pre)))}
    if i_ffc is not None:
        fk = track.knee(i_ffc, front)
        stride = np.linalg.norm(track.p(i_ffc, front["ankle"]) - track.p(i_ffc, arm["ankle"])) / H * 100
        m["ffc"] = {"front_knee": round(fk) if fk else 0, "stride_pct_height": round(stride)}
        m["delivery_stride"] = {"stride_pct_height": round(stride)}
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
    if i_rel is not None:
        ground = max(track.xy[i_rel, 15, 1], track.xy[i_rel, 16, 1])
        rel_h = (ground - track.xy[i_rel, arm["wrist"], 1]) / H * 100
        m["finger_roll_release"] = {"release_height_pct": round(rel_h)}
        m["wrist_snap"] = {"release_height_pct": round(rel_h)}
        post = track.range(ev["release"], ev["release"] + 0.15)
        if len(post):
            m["forward_trunk_flexion"] = {"forward_lean_max": round(max(0, max(track.trunk_lean(i) for i in post)))}
        # elbow: compare arm at horizontal (before release) with release - large drop of flexion = possible straightening
        if i_ffc is not None:
            ids = range(i_ffc, i_rel + 1)
            elb = [(i, track.joint(i, arm["shoulder"], arm["elbow"], arm["wrist"])) for i in ids]
            elb = [(i, v) for i, v in elb if v]
            if elb:
                horiz = min(elb, key=lambda iv: abs(track.xy[iv[0], arm["wrist"], 1] - track.xy[iv[0], arm["shoulder"], 1]))
                rel_el = elb[-1][1]
                m["arm_circumduction"] = {"elbow_at_horizontal": round(horiz[1]), "elbow_at_release": round(rel_el),
                                          "elbow_extension_est": round(max(0, rel_el - horiz[1]))}
    # approach speed estimate (assumes a 1.80 m bowler and a side-on, static camera)
    if "take_off" in real:
        ids = track.range(ev["take_off"] - 0.6, ev["take_off"])
        if len(ids) >= 3:
            hx = (track.xy[ids, 11, 0] + track.xy[ids, 12, 0]) / 2
            dt = track.t[ids[-1]] - track.t[ids[0]]
            if dt > 0.15:
                ms = abs(hx[-1] - hx[0]) / H * 1.8 / dt
                if 1 < ms < 12:
                    m["peak_approach_velocity"] = {"approach_speed_ms": round(ms, 1)}
    return m


def measured_text(ev, meas):
    lines = [f"Detected events (s): take_off={ev['take_off']:.2f}, BFC={ev['bfc']:.2f}, FFC={ev['ffc']:.2f}, release={ev['release']:.2f}"
             f" (measured from skeleton: {', '.join(ev['measured']) or 'none - estimated'})"]
    lines.append(f"BFC->FFC {ev['ffc'] - ev['bfc']:.2f}s, FFC->release {ev['release'] - ev['ffc']:.2f}s")
    for key, vals in meas.items():
        lines.append(f"{key}: " + ", ".join(f"{k}={v}" for k, v in vals.items()))
    return "\n".join(lines)
