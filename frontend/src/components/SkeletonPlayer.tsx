import { useEvent } from "expo";
import { useVideoPlayer, VideoView } from "expo-video";
import { useEffect, useMemo, useState } from "react";
import { LayoutChangeEvent, Pressable, Text, View } from "react-native";
import Svg, { Circle, Line, Text as SvgText } from "react-native-svg";

import { mediaUrl, PoseData, Step, useDeviceId } from "@/src/api";
import { fonts, radius, space } from "@/src/constants";
import { proPose, travelDirection } from "@/src/proModel";
import { Ionicons } from "@/src/components/ui";
import { makeStyles, useTheme } from "@/src/theme";

// COCO-17 skeleton
const EDGES: [number, number][] = [
  [5, 6], [5, 7], [7, 9], [6, 8], [8, 10], [5, 11], [6, 12], [11, 12], [11, 13], [13, 15], [12, 14], [14, 16],
];
const SPEEDS = [1, 0.5, 0.25];
const MAX_H = 460;

type Props = {
  analysisId: string;
  meta: { width?: number; height?: number; duration?: number };
  steps: Step[];
  pose?: PoseData;
  bowlingArm: string;
  selected: number | null;
  seekNonce: number;
  onSelect: (i: number) => void;
  compact?: boolean;
};

export function SkeletonPlayer(props: Props) {
  const deviceId = useDeviceId();
  const s = useStyles();
  if (!deviceId) return <View style={[s.box, { height: 240 }]} />;
  return <PlayerInner {...props} deviceId={deviceId} />;
}

function interpolate(frames: PoseData["frames"], t: number): number[][] | null {
  if (!frames.length) return null;
  let lo = 0, hi = frames.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1;
    if (frames[mid].t <= t) lo = mid; else hi = mid - 1;
  }
  const a = frames[lo], b = frames[lo + 1];
  const ak = a.display_k ?? a.k;
  const bk = b ? (b.display_k ?? b.k) : null;
  if (!ak) return bk && b && b.t - t < 0.1 ? bk : null;
  if (!b || !bk || b.t === a.t) return t - a.t < 0.2 ? ak : null;
  const r = Math.min(1, Math.max(0, (t - a.t) / (b.t - a.t)));
  return ak.map((p, i) => [p[0] + (bk[i][0] - p[0]) * r, p[1] + (bk[i][1] - p[1]) * r, Math.min(p[2], bk[i][2])]);
}

function PlayerInner({ analysisId, meta, steps, pose, bowlingArm, selected, seekNonce, onSelect, deviceId, compact }: Props & { deviceId: string }) {
  const s = useStyles();
  const { colors } = useTheme();
  const [width, setWidth] = useState(0);
  const [speedIdx, setSpeedIdx] = useState(1);
  const [showSkeleton, setShowSkeleton] = useState(true);
  const [showPro, setShowPro] = useState(!!compact);

  const player = useVideoPlayer({ uri: mediaUrl(analysisId, deviceId) }, (p) => {
    p.loop = true;
    p.muted = true;
    p.timeUpdateEventInterval = 0.04;
    p.playbackRate = 0.5;
    p.play();
  });
  const { currentTime } = useEvent(player, "timeUpdate", { currentTime: player.currentTime } as any) as { currentTime: number };
  const { isPlaying } = useEvent(player, "playingChange", { isPlaying: player.playing });

  const duration = player.duration || meta.duration || 1;
  const aspect = meta.width && meta.height ? meta.width / meta.height : 16 / 9;
  let boxW = width, boxH = width / aspect;
  const maxH = compact ? 320 : MAX_H;
  if (boxH > maxH) {
    boxH = maxH;
    boxW = maxH * aspect;
  }

  const [pausedAt, setPausedAt] = useState<number | null>(null);
  const [pendingSeek, setPendingSeek] = useState<number | null>(null);
  const { status } = useEvent(player, "statusChange", { status: player.status } as any) as { status: string };
  useEffect(() => {
    if (selected == null) return;
    const t = steps[selected]?.t;
    if (t == null) return;
    player.pause();
    setPausedAt(t);
    setPendingSeek(t);
  }, [seekNonce]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    // Web drops seeks issued before the video is loaded, so hold the seek until it's ready.
    if (pendingSeek == null || status !== "readyToPlay") return;
    player.pause();
    player.currentTime = pendingSeek;
    setPendingSeek(null);
  }, [pendingSeek, status, player]);
  const time = !isPlaying && pausedAt != null ? pausedAt : currentTime ?? 0;

  const right = bowlingArm.toLowerCase().startsWith("r");
  const armEdges = right ? ["6-8", "8-10"] : ["5-7", "7-9"];
  const frontLegEdges = right ? ["11-13", "13-15"] : ["12-14", "14-16"];
  const kp = useMemo(() => (pose ? interpolate(pose.frames, time) : null), [pose, time]);

  const step = selected != null ? steps[selected] : null;
  const atStep = step?.t != null && Math.abs(time - step.t) < 0.15;
  const dir = useMemo(() => (pose ? travelDirection(pose.frames) : 1), [pose]);
  const refStep = atStep && step ? step : [...steps].reverse().find((st) => st.t != null && st.t <= time + 0.05) ?? steps.find((st) => st.t != null);
  const ghost = showPro && kp && refStep ? proPose(refStep.key, kp, boxW, boxH, dir, !right) : null;
  const label = (idx: number, value?: number) => {
    if (!kp || value == null || kp[idx][2] < 0.3) return null;
    return (
      <SvgText x={kp[idx][0] * boxW + 10} y={kp[idx][1] * boxH + 5} fill={colors.accent} stroke={colors.surface} strokeWidth={0.8} fontSize={16} fontWeight="bold">
        {`${value}°`}
      </SvgText>
    );
  };

  const togglePlay = () => {
    if (isPlaying) player.pause();
    else {
      setPausedAt(null);
      player.play();
    }
  };
  const cycleSpeed = () => {
    const next = (speedIdx + 1) % SPEEDS.length;
    setSpeedIdx(next);
    player.playbackRate = SPEEDS[next];
  };
  const visibleSteps = steps.map((st, i) => ({ st, i })).filter((x) => x.st.t != null);
  const jump = (dir: 1 | -1) => {
    const cur = selected ?? -1;
    const list = dir === 1 ? visibleSteps.filter((x) => x.i > cur) : visibleSteps.filter((x) => x.i < cur).reverse();
    if (list[0]) onSelect(list[0].i);
  };

  return (
    <View onLayout={(e: LayoutChangeEvent) => setWidth(e.nativeEvent.layout.width)} testID="skeleton-player">
      {width > 0 ? (
        <View style={[s.box, { width: boxW, height: boxH, alignSelf: "center" }]}>
          <VideoView player={player} style={{ width: boxW, height: boxH }} contentFit="contain" nativeControls={false} />
          {showSkeleton && kp ? (
            <Svg width={boxW} height={boxH} style={s.overlay} pointerEvents="none" testID="skeleton-overlay">
              {ghost ? (
                <>
                  {EDGES.map(([a, b]) => (
                    <Line key={`gs${a}-${b}`} x1={ghost[a][0]} y1={ghost[a][1]} x2={ghost[b][0]} y2={ghost[b][1]} stroke={colors.surface} strokeWidth={6} strokeLinecap="round" opacity={0.7} />
                  ))}
                  {EDGES.map(([a, b]) => (
                    <Line key={`g${a}-${b}`} x1={ghost[a][0]} y1={ghost[a][1]} x2={ghost[b][0]} y2={ghost[b][1]} stroke={colors.silver} strokeWidth={3} strokeDasharray="6 4" strokeLinecap="round" opacity={0.85} />
                  ))}
                  <Circle cx={ghost[0][0]} cy={ghost[0][1]} r={9} fill="none" stroke={colors.silver} strokeWidth={2} strokeDasharray="4 3" />
                </>
              ) : null}
              {EDGES.map(([a, b]) => {
                if (kp[a][2] < 0.3 || kp[b][2] < 0.3) return null;
                const id = `${a}-${b}`;
                const stroke = armEdges.includes(id) ? colors.accent : frontLegEdges.includes(id) ? colors.info : colors.onSurface;
                return <Line key={id} x1={kp[a][0] * boxW} y1={kp[a][1] * boxH} x2={kp[b][0] * boxW} y2={kp[b][1] * boxH} stroke={stroke} strokeWidth={compact ? 2.5 : 4} strokeLinecap="round" />;
              })}
              {kp.slice(5).map((p, i) => (p[2] < 0.3 ? null : <Circle key={i} cx={p[0] * boxW} cy={p[1] * boxH} r={compact ? 2 : 4} fill={colors.surface} stroke={colors.onSurface} strokeWidth={compact ? 1 : 2} />))}
              {kp[0][2] > 0.3 ? <Circle cx={kp[0][0] * boxW} cy={kp[0][1] * boxH} r={compact ? 6 : 10} fill="none" stroke={colors.onSurface} strokeWidth={compact ? 2 : 3} /> : null}
              {atStep && step && !compact ? (
                <>
                  {label(right ? 13 : 14, step.metrics.front_knee)}
                  {label(right ? 8 : 7, step.metrics.bowling_elbow)}
                </>
              ) : null}
            </Svg>
          ) : null}
          {step && !compact ? (
            <View style={s.stepBadge} pointerEvents="none">
              <Text style={s.stepBadgeText} numberOfLines={1}>{selected! + 1}. {step.name}</Text>
            </View>
          ) : null}
        </View>
      ) : null}

      {!compact ? (<>
      <View style={s.scrub}>
        <View style={s.track} />
        <View style={[s.played, { width: `${Math.min(100, (time / duration) * 100)}%` }]} />
        {visibleSteps.map(({ st, i }) => (
          <Pressable
            key={st.key}
            testID={`timeline-marker-${st.key}`}
            hitSlop={8}
            onPress={() => onSelect(i)}
            style={[s.marker, { left: `${(st.t! / duration) * 100}%`, backgroundColor: i === selected ? colors.accent : st.status === "fault" ? colors.error : st.status === "good" ? colors.success : colors.warning }, i === selected && s.markerActive]}
          />
        ))}
      </View>

      <View style={s.controls}>
        <Pressable testID="player-prev-step" style={s.ctrl} onPress={() => jump(-1)}>
          <Ionicons name="play-skip-back" size={18} color={colors.onSurface} />
        </Pressable>
        <Pressable testID="player-play-toggle" style={[s.ctrl, s.ctrlMain]} onPress={togglePlay}>
          <Ionicons name={isPlaying ? "pause" : "play"} size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Pressable testID="player-next-step" style={s.ctrl} onPress={() => jump(1)}>
          <Ionicons name="play-skip-forward" size={18} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }} />
        <Pressable testID="player-speed-toggle" style={s.pillBtn} onPress={cycleSpeed}>
          <Text style={s.pillText}>{SPEEDS[speedIdx]}x</Text>
        </Pressable>
        <Pressable testID="player-pro-toggle" style={[s.pillBtn, showPro && s.pillOn]} onPress={() => setShowPro((v) => !v)}>
          <Ionicons name="git-compare" size={14} color={colors.onSurface} />
          <Text style={s.pillText}>Pro</Text>
        </Pressable>
        <Pressable testID="player-skeleton-toggle" style={[s.pillBtn, showSkeleton && s.pillOn]} onPress={() => setShowSkeleton((v) => !v)}>
          <Ionicons name="body" size={14} color={showSkeleton ? colors.onBrandPrimary : colors.onSurface} />
          
        </Pressable>
      </View>
      {showPro ? <Text style={s.hint}>Dashed silver = elite reference model at {refStep ? refStep.name : "this step"}, scaled to your body.</Text> : null}
      </>) : null}
      {!pose ? <Text style={s.hint}>Body tracking unavailable for this clip — film side-on with the full body in frame.</Text> : null}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  box: { borderRadius: radius.lg, overflow: "hidden", backgroundColor: c.surfaceSecondary },
  overlay: { position: "absolute", top: 0, left: 0 },
  stepBadge: { position: "absolute", left: space.sm, top: space.sm, right: space.sm, alignSelf: "flex-start", backgroundColor: c.scrim, borderRadius: radius.pill, paddingHorizontal: space.md, paddingVertical: 6, maxWidth: "90%" },
  stepBadgeText: { fontFamily: fonts.textBold, fontSize: 12, color: c.onSurface },
  scrub: { height: 28, justifyContent: "center", marginTop: space.md, marginHorizontal: space.sm },
  track: { position: "absolute", left: 0, right: 0, height: 4, borderRadius: 2, backgroundColor: c.surfaceTertiary },
  played: { position: "absolute", left: 0, height: 4, borderRadius: 2, backgroundColor: c.brandSecondary },
  marker: { position: "absolute", width: 10, height: 10, borderRadius: 5, marginLeft: -5, borderWidth: 1, borderColor: c.surface },
  markerActive: { width: 16, height: 16, borderRadius: 8, marginLeft: -8 },
  controls: { flexDirection: "row", alignItems: "center", gap: space.sm, marginTop: space.sm },
  ctrl: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  ctrlMain: { backgroundColor: c.brandPrimary, width: 52, height: 52, borderRadius: 26 },
  pillBtn: { height: 44, minWidth: 44, justifyContent: "center", paddingHorizontal: space.md, borderRadius: radius.pill, backgroundColor: c.surfaceTertiary, flexDirection: "row", alignItems: "center", gap: 6 },
  pillOn: { backgroundColor: c.brandPrimary },
  pillText: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurface },
  hint: { fontFamily: fonts.text, fontSize: 12, color: c.muted, marginTop: space.sm },
}));
