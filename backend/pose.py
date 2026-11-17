"""Server-side body tracking with RTMPose (rtmlib + onnxruntime, COCO 17 keypoints per frame).

Every person in each frame is detected, people are linked into tracks across frames, and the
bowler is chosen as the track that moves the most (run-up + delivery) while staying large and
confident. Short gaps are filled and the keypoints are lightly smoothed so the skeleton never
jumps to the umpire, batter or a fielder.
"""
import math
import os
import threading

import cv2
import numpy as np

# COCO-17 indices
L = {"shoulder": 5, "elbow": 7, "wrist": 9, "hip": 11, "knee": 13, "ankle": 15}
R = {"shoulder": 6, "elbow": 8, "wrist": 10, "hip": 12, "knee": 14, "ankle": 16}


def _normalise_bowling_arm(bowling_arm):
    """Use a safe right-arm default for missing or unrecognised profile values."""
    label = str(bowling_arm or "right").strip().lower()
    return "right" if label.startswith("r") or not label.startswith("l") else "left"


POSE_MODE = os.environ.get("POSE_MODE", "performance")  # performance | balanced | lightweight
_lock = threading.Lock()
_body = None


def _get_body():
    global _body
    with _lock:
        if _body is None:
            from rtmlib import Body
            _body = Body(mode=POSE_MODE, backend="onnxruntime", device="cpu")
        return _body


def warmup():
    _get_body()


def _safe_fps(value, default: float = 30.0) -> float:
    try:
        fps = float(value)
    except (TypeError, ValueError):
        return default
    return fps if math.isfinite(fps) and fps > 0 else default


def assess_video_quality(frames, fps: float, width: int, height: int) -> dict:
    """Screen capture quality with transparent heuristics; this is not a calibrated quality score."""
    flags = []
    if min(width, height) < 480:
        flags.append("low_resolution")
    if not math.isfinite(float(fps)) or fps < 24:
        flags.append("low_frame_rate")

    luminance, sharpness = [], []
    for frame in frames:
        if frame is None or not getattr(frame, "size", 0):
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        luminance.append(float(np.mean(gray)))
        sharpness.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))

    mean_luminance = float(np.mean(luminance)) if luminance else None
    median_sharpness = float(np.median(sharpness)) if sharpness else None
    if mean_luminance is not None and mean_luminance < 35:
        flags.append("low_light")
    elif mean_luminance is not None and mean_luminance > 220:
        flags.append("overexposed")
    if median_sharpness is not None and median_sharpness < 35:
        flags.append("possible_blur_or_motion_blur")
    if not luminance:
        flags.append("quality_sampling_unavailable")

    return {
        "rating": "review" if flags else "good",
        "flags": flags,
        "samples": len(luminance),
        "mean_luminance": round(mean_luminance, 1) if mean_luminance is not None else None,
        "median_sharpness": round(median_sharpness, 1) if median_sharpness is not None else None,
        "method": "screening_heuristics_not_calibrated",
    }


def video_meta(path: str) -> dict:
    cap = cv2.VideoCapture(path)
    fps = _safe_fps(cap.get(cv2.CAP_PROP_FPS))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    sample_frames = []
    if total > 0:
        for index in np.linspace(0, max(0, total - 1), min(8, total), dtype=int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = cap.read()
            if ok:
                sample_frames.append(frame)
    cap.release()
    duration = round(total / fps, 2) if total else 0
    return {
        "fps": round(fps, 2), "duration": duration, "width": width, "height": height,
        "quality": assess_video_quality(sample_frames, fps, width, height),
    }


def _bbox(kp, sc):
    good = kp[sc > 0.3] if (sc > 0.3).sum() >= 4 else kp
    x0, y0 = good.min(0)
    x1, y1 = good.max(0)
    return np.array([x0, y0, x1, y1], dtype=float)


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _link(dets, diag, times=None, max_gap_seconds: float = 0.35):
    """Associate detections only across short real-time gaps using IoU + centre distance."""
    tracks = []  # each: {"last": fi, "box": bbox, "vel": (dx, dy), "dets": {fi: det}}
    for fi, people in enumerate(dets):
        pairs = []
        for ti, tr in enumerate(tracks):
            gap = fi - tr["last"]
            elapsed = (float(times[fi]) - float(times[tr["last"]])) if times is not None else gap / 60.0
            if gap <= 0 or elapsed <= 0 or elapsed > max_gap_seconds:
                continue
            pred = tr["box"] + np.array([*tr["vel"], *tr["vel"]]) * gap
            pc = ((pred[0] + pred[2]) / 2, (pred[1] + pred[3]) / 2)
            for pi, d in enumerate(people):
                c = ((d["box"][0] + d["box"][2]) / 2, (d["box"][1] + d["box"][3]) / 2)
                dist = math.hypot(c[0] - pc[0], c[1] - pc[1]) / diag
                iou = _iou(pred, d["box"])
                if iou > 0.05 or dist < 0.12 * gap:
                    pairs.append((iou - dist, ti, pi))
        used_t, used_p = set(), set()
        for _, ti, pi in sorted(pairs, reverse=True):
            if ti in used_t or pi in used_p:
                continue
            tr, d = tracks[ti], people[pi]
            gap = fi - tr["last"]
            oc = (tr["box"][:2] + tr["box"][2:]) / 2
            nc = (d["box"][:2] + d["box"][2:]) / 2
            v = (nc - oc) / gap
            tr["vel"] = (0.6 * v[0] + 0.4 * tr["vel"][0], 0.6 * v[1] + 0.4 * tr["vel"][1])
            tr["box"], tr["last"] = d["box"], fi
            tr["dets"][fi] = d
            used_t.add(ti)
            used_p.add(pi)
        for pi, d in enumerate(people):
            if pi not in used_p:
                tracks.append({"last": fi, "box": d["box"], "vel": (0.0, 0.0), "dets": {fi: d}})
    return tracks


def _bowler_score(tr, diag):
    """Bowler = long-lived, large, confident and the most mobile (run-up + whipping arm)."""
    items = sorted(tr["dets"].items())
    if len(items) < 3:
        return 0.0
    centres = np.array([(d["box"][:2] + d["box"][2:]) / 2 for _, d in items])
    travel = float(np.abs(np.diff(centres, axis=0)).sum()) / diag
    limbs = [d["kp"][[7, 8, 9, 10, 13, 14, 15, 16]] for _, d in items]
    limb_motion = float(np.mean([np.linalg.norm(b - a, axis=1).mean() for a, b in zip(limbs, limbs[1:])])) / diag
    size = float(np.mean([(d["box"][3] - d["box"][1]) for _, d in items])) / diag
    conf = float(np.mean([d["sc"].mean() for _, d in items]))
    return len(items) * conf * (0.4 + size) * (1 + 3 * travel + 25 * limb_motion)


def _subject_selection_confidence(tracks, selected, diag) -> dict:
    """Flag clips where another simultaneously visible person competes with the selected bowler track."""
    if not selected or not selected.get("dets"):
        return {"confidence": "low", "competing_tracks": 0}
    selected_frames = set(selected["dets"])
    selected_score = _bowler_score(selected, diag)
    strongest_ratio, competitors = 0.0, 0

    for track in tracks:
        if track is selected or not track.get("dets"):
            continue
        frames = set(track["dets"])
        # Compare detections on the same sampled frames, not just overlapping
        # first/last-frame ranges; sparse fragments are not simultaneous people.
        shared_frames = selected_frames & frames
        overlap_ratio = len(shared_frames) / max(1, min(len(selected_frames), len(frames)))
        if overlap_ratio < 0.4:
            continue
        competitors += 1
        ratio = _bowler_score(track, diag) / max(selected_score, 1e-6)
        strongest_ratio = max(strongest_ratio, ratio)

    confidence = "low" if strongest_ratio >= 0.85 else "medium" if strongest_ratio >= 0.65 else "high"
    return {"confidence": confidence, "competing_tracks": competitors}


def _smooth(kps, scs):
    """Confidence-weighted 3-frame smoothing that keeps fast arm motion intact."""
    out = kps.copy()
    n = len(kps)
    for i in range(1, n - 1):
        w = np.stack([scs[i - 1], scs[i] * 2, scs[i + 1]])[..., None]
        blend = (np.stack([kps[i - 1], kps[i], kps[i + 1]]) * w).sum(0) / np.maximum(w.sum(0), 1e-6)
        jump = np.linalg.norm(kps[i + 1] - kps[i - 1], axis=1, keepdims=True)
        # only smooth where motion is small (jitter), keep large motion (the bowling arm) raw
        alpha = np.clip(1 - jump / 40.0, 0, 1) * 0.6
        out[i] = kps[i] * (1 - alpha) + blend * alpha
    return out


def extract_pose(path: str, target_fps: int = 60, max_frames: int = 1200) -> dict:
    body = _get_body()
    cap = cv2.VideoCapture(path)
    fps = _safe_fps(cap.get(cv2.CAP_PROP_FPS))
    target_fps = max(1, int(target_fps or 60))
    step = max(1, round(fps / target_fps))
    dets, times, width, height, sw, sh, i = [], [], 0, 0, 1, 1, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            height, width = frame.shape[:2]
            scale = 960 / max(width, height)
            small = cv2.resize(frame, (int(width * scale), int(height * scale))) if scale < 1 else frame
            sh, sw = small.shape[:2]
            with _lock:
                keypoints, scores = body(small)
            people = []
            for kp, sc in zip(keypoints, scores):
                kp, sc = np.asarray(kp, float), np.asarray(sc, float)
                if sc.mean() >= 0.25:
                    people.append({"kp": kp, "sc": sc, "box": _bbox(kp, sc)})
            dets.append(people)
            times.append(round(i / fps, 3))
            if len(dets) >= max_frames:
                break
        i += 1
    cap.release()

    diag = math.hypot(sw, sh)
    tracks = _link(dets, diag, times=times)
    n = len(dets)
    frames = [{"t": t, "k": None} for t in times]
    observed = np.zeros(n, bool)
    selection_quality = {"confidence": "low", "competing_tracks": 0}
    if tracks:
        bowler = max(tracks, key=lambda tr: _bowler_score(tr, diag))
        selection_quality = _subject_selection_confidence(tracks, bowler, diag)
        # stitch: re-attach fragments that continue the bowler where his track broke (occlusion)
        for tr in sorted(tracks, key=lambda tr: min(tr["dets"])):
            if tr is bowler:
                continue
            fr = set(tr["dets"])
            if fr & set(bowler["dets"]):
                continue
            first, last = min(fr), max(fr)
            before = [f for f in bowler["dets"] if f < first]
            after = [f for f in bowler["dets"] if f > last]
            ref = bowler["dets"][max(before)] if before else (bowler["dets"][min(after)] if after else None)
            gapf = (first - max(before)) if before else (min(after) - last if after else 99)
            if ref is None or gapf > 12:
                continue
            d = tr["dets"][first] if before else tr["dets"][last]
            rc, dc = (ref["box"][:2] + ref["box"][2:]) / 2, (d["box"][:2] + d["box"][2:]) / 2
            rh, dh = ref["box"][3] - ref["box"][1], d["box"][3] - d["box"][1]
            if np.linalg.norm(rc - dc) / diag < 0.06 * gapf + 0.05 and 0.6 < dh / max(rh, 1) < 1.6:
                bowler["dets"].update(tr["dets"])

        idx = sorted(bowler["dets"])
        kps = np.zeros((n, 17, 2))
        scs = np.zeros((n, 17))
        have = np.zeros(n, bool)
        for fi in idx:
            kps[fi], scs[fi], have[fi], observed[fi] = bowler["dets"][fi]["kp"], bowler["dets"][fi]["sc"], True, True
        # fill short gaps (<= 4 frames) by linear interpolation between the bowler's poses
        for a, b in zip(idx, idx[1:]):
            if 1 < b - a <= 5:
                for fi in range(a + 1, b):
                    r = (fi - a) / (b - a)
                    kps[fi] = kps[a] * (1 - r) + kps[b] * r
                    # Interpolated joints are useful for a continuous overlay, but are not observations.
                    # Keep their confidence below the measurement threshold so they cannot drive biomechanics.
                    scs[fi] = np.minimum(scs[a], scs[b]) * 0.4
                    have[fi] = True
        kps = _smooth(kps, scs)
        for fi in range(n):
            if have[fi] and scs[fi].mean() >= 0.25:
                frames[fi]["k"] = [[round(float(x) / sw, 4), round(float(y) / sh, 4), round(float(s), 2)]
                                   for (x, y), s in zip(kps[fi], scs[fi])]
    detected = int(observed.sum())
    pose_frames = sum(1 for f in frames if f["k"])
    interpolated_frames = max(0, pose_frames - detected)
    critical = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
    observed_scores = [frames[i]["k"][j][2] for i in range(len(frames)) if observed[i] and frames[i]["k"] for j in critical]
    critical_slots = max(1, detected * len(critical))
    reliable_slots = sum(1 for i in range(len(frames)) if observed[i] and frames[i]["k"]
                         for j in critical if frames[i]["k"][j][2] >= 0.45)
    coverage = detected / max(1, len(frames))
    joint_coverage = reliable_slots / critical_slots
    mean_confidence = float(np.mean(observed_scores)) if observed_scores else 0.0
    quality = "good" if coverage >= 0.80 and joint_coverage >= 0.70 and mean_confidence >= 0.55 else (
        "usable" if coverage >= 0.50 and joint_coverage >= 0.45 and mean_confidence >= 0.40 else "limited"
    )
    if selection_quality["confidence"] == "low":
        quality = "limited"
    elif selection_quality["confidence"] == "medium" and quality == "good":
        quality = "usable"
    return {
        "width": width, "height": height, "frames": frames, "detected": detected,
        "source_fps": round(float(fps), 2), "sampled_fps": round(float(fps / step), 2),
        "quality": {
            "rating": quality, "frame_count": len(frames), "detected_frames": detected,
            "interpolated_frames": interpolated_frames, "frame_coverage": round(coverage, 3),
            "critical_joint_coverage": round(joint_coverage, 3),
            "mean_joint_confidence": round(mean_confidence, 3),
            "subject_selection_confidence": selection_quality["confidence"],
            "competing_tracks": selection_quality["competing_tracks"],
        },
    }


def _angle(a, b, c, w, h, min_segment_px=1e-6):
    """Return a camera-plane joint angle, or None for degenerate geometry."""
    ax, ay = (a[0] - b[0]) * w, (a[1] - b[1]) * h
    cx, cy = (c[0] - b[0]) * w, (c[1] - b[1]) * h
    na, nc = math.hypot(ax, ay), math.hypot(cy, cx)
    if na < min_segment_px or nc < min_segment_px:
        return None
    return round(math.degrees(math.acos(max(-1, min(1, (ax * cx + ay * cy) / (na * nc))))))


def _joint_confident(k, *indices, threshold: float = 0.45) -> bool:
    """A metric is valid only when every keypoint it depends on was confidently observed."""
    try:
        return all(len(k[index]) >= 3 and float(k[index][2]) >= threshold for index in indices)
    except (IndexError, TypeError, ValueError):
        return False


def _metrics(k, w, h, bowling_arm: str) -> dict:
    arm = R if _normalise_bowling_arm(bowling_arm) == "right" else L
    front = L if arm is R else R
    front_joints = (front["hip"], front["knee"], front["ankle"])
    back_joints = (arm["hip"], arm["knee"], arm["ankle"])
    elbow_joints = (arm["shoulder"], arm["elbow"], arm["wrist"])
    trunk_joints = (5, 6, 11, 12)
    height_joints = (0, 5, 6, 11, 12, 13, 14, 15, 16)
    if _joint_confident(k, *height_joints):
        sx, sy = (k[5][0] + k[6][0]) / 2, (k[5][1] + k[6][1]) / 2
        hx, hy = (k[11][0] + k[12][0]) / 2, (k[11][1] + k[12][1]) / 2
        leg = (math.dist(k[11][:2], k[13][:2]) + math.dist(k[13][:2], k[15][:2]) +
               math.dist(k[12][:2], k[14][:2]) + math.dist(k[14][:2], k[16][:2])) * 0.5
        body_height = (math.dist(k[0][:2], (sx, sy)) + math.dist((sx, sy), (hx, hy)) + leg) * math.hypot(w, h) * 0.5 * 1.12
    else:
        body_height = h * 0.5
    min_segment_px = max(2.0, body_height * 0.025)

    result = {
        "front_knee": _angle(k[front["hip"]], k[front["knee"]], k[front["ankle"]], w, h, min_segment_px)
        if _joint_confident(k, *front_joints) else None,
        "back_knee": _angle(k[arm["hip"]], k[arm["knee"]], k[arm["ankle"]], w, h, min_segment_px)
        if _joint_confident(k, *back_joints) else None,
        "bowling_elbow": _angle(k[arm["shoulder"]], k[arm["elbow"]], k[arm["wrist"]], w, h, min_segment_px)
        if _joint_confident(k, *elbow_joints) else None,
        "trunk_lean": None,
    }
    if _joint_confident(k, *trunk_joints):
        sx = (k[5][0] + k[6][0]) / 2
        sy = (k[5][1] + k[6][1]) / 2
        hx = (k[11][0] + k[12][0]) / 2
        hy = (k[11][1] + k[12][1]) / 2
        dx, dy = (sx - hx) * w, (sy - hy) * h
        if abs(dy) > 1e-6:
            result["trunk_lean"] = round(math.degrees(math.atan2(abs(dx), abs(dy))))
    return result


def metrics_at(pose: dict, t, bowling_arm: str) -> dict:
    """Confidence-gated 2D joint angles only near the requested timestamp."""
    frames = [f for f in pose.get("frames", []) if f.get("k")]
    if not frames or t is None:
        return {}
    f = min(frames, key=lambda x: abs(x["t"] - t))
    times = np.array([float(frame["t"]) for frame in frames], dtype=float)
    intervals = np.diff(times)
    intervals = intervals[intervals > 0]
    tolerance = min(0.2, max(0.04, 1.5 * float(np.median(intervals)))) if len(intervals) else 0.04
    if abs(float(f["t"]) - float(t)) > tolerance:
        return {}
    return _metrics(f["k"], pose.get("width") or 1, pose.get("height") or 1, bowling_arm)


def timeline_text(pose: dict, bowling_arm: str, every: float = 0.08) -> str:
    """Confidence-gated camera-plane measurements for the AI analyst; unavailable values stay unavailable."""
    frames = [f for f in pose.get("frames", []) if f.get("k")]
    if not frames:
        return "No reliable skeleton measurements available."
    w, h = pose.get("width") or 1, pose.get("height") or 1
    arm = R if _normalise_bowling_arm(bowling_arm) == "right" else L
    rows, last_t = [], -1.0
    for f in frames:
        if f["t"] - last_t < every:
            continue
        last_t = f["t"]
        k = f["k"]
        m = _metrics(k, w, h, bowling_arm)
        wrist_above_nose = "na"
        if _joint_confident(k, arm["wrist"], 0):
            wrist_above_nose = "y" if k[arm["wrist"]][1] < k[0][1] else "n"
        hip_x = f"{(k[11][0] + k[12][0]) / 2:.2f}" if _joint_confident(k, 11, 12) else "na"
        fmt = lambda value: "na" if value is None else str(value)
        rows.append(
            f"t={f['t']:.2f} fk={fmt(m['front_knee'])} bk={fmt(m['back_knee'])} "
            f"el={fmt(m['bowling_elbow'])} lean={fmt(m['trunk_lean'])} "
            f"wrist_above_nose={wrist_above_nose} hip_x={hip_x}"
        )
    return "\n".join(rows)
