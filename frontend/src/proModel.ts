// Elite biomechanical reference model ("Pro" ghost skeleton) for a right-arm fast bowler running
// toward +x, filmed side-on. Units: torso length (hip-centre → shoulder-centre) = 1, origin at hip centre,
// y grows downward. COCO-17 joints: 0 nose, 5/6 shoulders, 7/8 elbows, 9/10 wrists, 11/12 hips, 13/14 knees, 15/16 ankles.
// L = front (non-bowling) side, R = bowling side.
type P = [number, number];
type Template = { nose: P; sh: P; lelb: P; lwri: P; relb: P; rwri: P; lkn: P; lank: P; rkn: P; rank: P };

const T: Record<string, Template> = {
  run: { nose: [0.22, -1.35], sh: [0.1, -1], lelb: [0.35, -0.65], lwri: [0.55, -0.45], relb: [-0.2, -0.6], rwri: [-0.15, -0.3], lkn: [0.35, 0.45], lank: [0.3, 0.95], rkn: [-0.15, 0.5], rank: [-0.45, 0.8] },
  gather: { nose: [0.1, -1.35], sh: [0, -1], lelb: [0.25, -0.75], lwri: [0.15, -0.95], relb: [-0.15, -0.7], rwri: [0.05, -0.9], lkn: [0.3, 0.35], lank: [0.15, 0.8], rkn: [-0.1, 0.5], rank: [-0.25, 0.95] },
  bfc: { nose: [-0.05, -1.3], sh: [-0.15, -0.98], lelb: [0.15, -1.4], lwri: [0.35, -1.75], relb: [-0.45, -0.75], rwri: [-0.6, -0.45], lkn: [0.45, 0.25], lank: [0.55, 0.65], rkn: [-0.05, 0.5], rank: [-0.1, 1] },
  stride: { nose: [0, -1.3], sh: [-0.1, -0.97], lelb: [0.35, -1.25], lwri: [0.6, -1.4], relb: [-0.55, -0.6], rwri: [-0.85, -0.45], lkn: [0.6, 0.35], lank: [0.95, 0.75], rkn: [-0.3, 0.5], rank: [-0.55, 0.95] },
  ffc: { nose: [0.15, -1.33], sh: [0.05, -1], lelb: [0.45, -0.9], lwri: [0.55, -0.6], relb: [-0.4, -1.2], rwri: [-0.55, -1.6], lkn: [0.45, 0.45], lank: [0.8, 0.95], rkn: [-0.4, 0.45], rank: [-0.8, 0.75] },
  release: { nose: [0.5, -1.2], sh: [0.35, -0.92], lelb: [0.3, -0.4], lwri: [0.15, -0.1], relb: [0.35, -1.55], rwri: [0.4, -2], lkn: [0.35, 0.5], lank: [0.6, 1], rkn: [-0.35, 0.4], rank: [-0.75, 0.7] },
  follow: { nose: [0.85, -0.85], sh: [0.6, -0.7], lelb: [0.2, -0.3], lwri: [-0.05, -0.1], relb: [0.75, -0.25], rwri: [0.6, 0.2], lkn: [0.4, 0.5], lank: [0.5, 1], rkn: [0.25, 0.35], rank: [0, 0.75] },
  decel: { nose: [0.3, -1.3], sh: [0.2, -0.97], lelb: [0.3, -0.6], lwri: [0.45, -0.4], relb: [0.05, -0.6], rwri: [0.15, -0.3], lkn: [0.3, 0.45], lank: [0.25, 0.95], rkn: [-0.1, 0.5], rank: [-0.35, 0.85] },
};

const STEP_TEMPLATE: Record<string, keyof typeof T> = {
  run_up_acceleration: "run", peak_approach_velocity: "run", pre_delivery_stride: "run",
  take_off: "gather", gather: "gather", airborne_alignment: "gather",
  posterior_trunk_tilt: "bfc", bfc: "bfc", back_knee_compression: "bfc", counter_rotation: "bfc", front_arm_elevation: "bfc",
  delivery_stride: "stride",
  ffc: "ffc", front_knee_bracing: "ffc", pelvic_rotation: "ffc", hip_shoulder_separation: "ffc",
  front_arm_pull_down: "release", lateral_trunk_flexion: "release", forward_trunk_flexion: "release", arm_circumduction: "release",
  shoulder_internal_rotation: "release", wrist_extension: "release", wrist_snap: "release", finger_roll_release: "release",
  arm_follow_through: "follow", back_leg_swing: "follow", deceleration_strides: "decel",
};

/** Direction of travel in the clip: +1 if the bowler moves right on screen, -1 if left. */
export function travelDirection(frames: { t: number; k: number[][] | null }[]): 1 | -1 {
  const pts = frames.filter((f) => f.k).map((f) => (f.k![11][0] + f.k![12][0]) / 2);
  if (pts.length < 2) return 1;
  return pts[pts.length - 1] >= pts[0] ? 1 : -1;
}

/**
 * Builds the reference skeleton for a step, anchored on the bowler's own hip centre and scaled to their torso.
 * Returns 17 points in pixel space, or null if the bowler isn't tracked.
 */
export function proPose(stepKey: string, kp: number[][], w: number, h: number, dir: 1 | -1, leftArm: boolean): P[] | null {
  const t = T[STEP_TEMPLATE[stepKey] ?? "ffc"];
  if ([5, 6, 11, 12].some((i) => kp[i][2] < 0.3)) return null;
  const hx = ((kp[11][0] + kp[12][0]) / 2) * w, hy = ((kp[11][1] + kp[12][1]) / 2) * h;
  const sx = ((kp[5][0] + kp[6][0]) / 2) * w, sy = ((kp[5][1] + kp[6][1]) / 2) * h;
  const torso = Math.hypot(sx - hx, sy - hy);
  if (!torso) return null;
  const at = ([x, y]: P, dx = 0): P => [hx + (x + dx) * torso * dir, hy + y * torso];
  // front side = L for right-arm bowlers; swap index sets for left-armers
  const F = leftArm ? { sh: 6, elb: 8, wri: 10, hip: 12, kn: 14, ank: 16 } : { sh: 5, elb: 7, wri: 9, hip: 11, kn: 13, ank: 15 };
  const B = leftArm ? { sh: 5, elb: 7, wri: 9, hip: 11, kn: 13, ank: 15 } : { sh: 6, elb: 8, wri: 10, hip: 12, kn: 14, ank: 16 };
  const out: P[] = Array.from({ length: 17 }, () => [hx, hy] as P);
  out[0] = at(t.nose);
  out[F.sh] = at(t.sh, 0.05); out[B.sh] = at(t.sh, -0.05);
  out[F.elb] = at(t.lelb); out[F.wri] = at(t.lwri); out[B.elb] = at(t.relb); out[B.wri] = at(t.rwri);
  out[F.hip] = at([0.04, 0]); out[B.hip] = at([-0.04, 0]);
  out[F.kn] = at(t.lkn); out[F.ank] = at(t.lank); out[B.kn] = at(t.rkn); out[B.ank] = at(t.rank);
  return out;
}
