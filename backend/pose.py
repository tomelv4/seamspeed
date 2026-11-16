"""Server-side body tracking with RTMPose (rtmlib + onnxruntime, COCO 17 keypoints per frame)."""
import math
import threading

import cv2

# COCO-17 indices
L = {"shoulder": 5, "elbow": 7, "wrist": 9, "hip": 11, "knee": 13, "ankle": 15}
R = {"shoulder": 6, "elbow": 8, "wrist": 10, "hip": 12, "knee": 14, "ankle": 16}

_lock = threading.Lock()
_body = None


def _get_body():
    global _body
    with _lock:
        if _body is None:
            from rtmlib import Body
            _body = Body(mode="lightweight", backend="onnxruntime", device="cpu")
        return _body


def warmup():
    _get_body()


def video_meta(path: str) -> dict:
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    cap.release()
    return {"fps": round(fps, 2), "duration": round(total / fps, 2) if total else 0}


def extract_pose(path: str, target_fps: int = 12, max_frames: int = 220) -> dict:
    body = _get_body()
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, round(fps / target_fps))
    frames, width, height, i = [], 0, 0, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            height, width = frame.shape[:2]
            scale = 640 / max(width, height)
            small = cv2.resize(frame, (int(width * scale), int(height * scale))) if scale < 1 else frame
            sh, sw = small.shape[:2]
            kp = None
            with _lock:
                keypoints, scores = body(small)
            if len(keypoints):
                # pick the largest person (the bowler is usually the nearest)
                best = max(range(len(keypoints)), key=lambda j: (keypoints[j][:, 1].max() - keypoints[j][:, 1].min()) * float(scores[j].mean()))
                kp = [[round(float(x) / sw, 4), round(float(y) / sh, 4), round(float(s), 2)] for (x, y), s in zip(keypoints[best], scores[best])]
                if sum(p[2] for p in kp) / len(kp) < 0.3:
                    kp = None
            frames.append({"t": round(i / fps, 3), "k": kp})
            if len(frames) >= max_frames:
                break
        i += 1
    cap.release()
    return {"width": width, "height": height, "frames": frames, "detected": sum(1 for f in frames if f["k"])}


def _angle(a, b, c, w, h) -> int:
    ax, ay = (a[0] - b[0]) * w, (a[1] - b[1]) * h
    cx, cy = (c[0] - b[0]) * w, (c[1] - b[1]) * h
    na, nc = math.hypot(ax, ay), math.hypot(cx, cy)
    if not na or not nc:
        return 0
    return round(math.degrees(math.acos(max(-1, min(1, (ax * cx + ay * cy) / (na * nc))))))


def metrics_at(pose: dict, t, bowling_arm: str) -> dict:
    """Joint angles at the frame nearest to t. Front leg = opposite side to the bowling arm."""
    frames = [f for f in pose.get("frames", []) if f["k"]]
    if not frames or t is None:
        return {}
    f = min(frames, key=lambda x: abs(x["t"] - t))
    if abs(f["t"] - t) > 0.4:
        return {}
    k, w, h = f["k"], pose["width"] or 1, pose["height"] or 1
    arm = R if bowling_arm.lower().startswith("r") else L
    front = L if arm is R else R
    sx, sy = (k[5][0] + k[6][0]) / 2, (k[5][1] + k[6][1]) / 2
    hx, hy = (k[11][0] + k[12][0]) / 2, (k[11][1] + k[12][1]) / 2
    dx, dy = (sx - hx) * w, (sy - hy) * h
    return {
        "front_knee": _angle(k[front["hip"]], k[front["knee"]], k[front["ankle"]], w, h),
        "back_knee": _angle(k[arm["hip"]], k[arm["knee"]], k[arm["ankle"]], w, h),
        "bowling_elbow": _angle(k[arm["shoulder"]], k[arm["elbow"]], k[arm["wrist"]], w, h),
        "trunk_lean": round(math.degrees(math.atan2(abs(dx), abs(dy)))) if dy else 0,
    }
