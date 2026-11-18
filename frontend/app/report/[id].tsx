import { useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useRef, useState } from "react";
import { ScrollView, Text, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { apiSend, useAnalysis, usePose, useProfile } from "@/src/api";
import { SkeletonPlayer } from "@/src/components/SkeletonPlayer";
import { StepCard, StepList } from "@/src/components/StepBreakdown";
import { InjuryScanner } from "@/src/components/InjuryScanner";
import { fonts, phaseLabel, radius, space } from "@/src/constants";
import { ErrorBanner, Ionicons, Loading, Pill, PressScale, PrimaryButton, SectionTitle, riskColor, scoreColor } from "@/src/components/ui";
import { makeStyles, useTheme } from "@/src/theme";

export default function Report() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { id } = useLocalSearchParams<{ id: string }>();
  const q = useAnalysis(id);
  const a = q.data;
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [seekNonce, setSeekNonce] = useState(0);
  const scrollRef = useRef<any>(null);
  const pose = usePose(id, !!a?.has_pose);
  const profile = useProfile();
  const steps = a?.steps ?? [];
  const coachingPriorities = a?.coaching_priorities?.length
    ? a.coaching_priorities
    : (a?.faults ?? []).slice(0, 3).map((fault, index) => ({
        priority: index + 1, type: "fault" as const, step_key: fault.step_key ?? "",
        phase: fault.phase, title: fault.title, reason: fault.description,
        action: fault.fix, severity: fault.severity,
      }));
  const selectStep = (i: number, scrollTop = false) => {
    setSelected(i);
    setSeekNonce((n) => n + 1);
    if (scrollTop) scrollRef.current?.scrollTo({ y: 0, animated: true });
  };

  const remove = async () => {
    await apiSend(`/analyses/${id}`, "DELETE");
    qc.invalidateQueries();
    router.back();
  };

  const min = a?.pace_band?.min_kmh ?? 0;
  const max = a?.pace_band?.max_kmh ?? 0;
  const pct = (v: number) => `${Math.min(100, Math.max(0, ((v - 90) / 70) * 100))}%` as const;

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <PressScale testID="report-back-button" style={s.iconBtn} onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </PressScale>
        <Text style={s.headerTitle}>Delivery Report</Text>
        <PressScale testID="report-delete-button" style={s.iconBtn} onPress={() => setConfirmDelete((v) => !v)}>
          <Ionicons name="trash-outline" size={20} color={colors.onSurface} />
        </PressScale>
      </View>

      {q.isLoading ? (
        <Loading testID="report-loading" />
      ) : q.isError || !a ? (
        <View style={{ padding: space.lg }}>
          <ErrorBanner testID="report-error" message="Could not load this report." onRetry={() => q.refetch()} />
        </View>
      ) : (
        <ScrollView ref={scrollRef} contentContainerStyle={{ padding: space.lg, paddingBottom: insets.bottom + space.xl, gap: space.xl }}>
          {confirmDelete ? (
            <View style={s.confirm} testID="delete-confirm-card">
              <Text style={s.confirmText}>Delete this report permanently?</Text>
              <View style={{ flexDirection: "row", gap: space.sm }}>
                <PressScale testID="confirm-delete-button" style={[s.smallBtn, { backgroundColor: colors.error }]} onPress={remove}>
                  <Text style={s.smallBtnText}>Delete</Text>
                </PressScale>
                <PressScale testID="cancel-delete-button" style={[s.smallBtn, { backgroundColor: colors.surfaceTertiary }]} onPress={() => setConfirmDelete(false)}>
                  <Text style={s.smallBtnText}>Cancel</Text>
                </PressScale>
              </View>
            </View>
          ) : null}

          {a.analysis_quality?.pose ? (
            <View style={s.qualityCard} testID="analysis-quality-panel">
              <Text style={s.kicker}>ANALYSIS QUALITY · {String(a.analysis_quality.pose.rating ?? "unknown").toUpperCase()}</Text>
              <Text style={s.note}>
                Pose coverage {Math.round((a.analysis_quality.pose.frame_coverage ?? 0) * 100)}% ·
                critical-joint coverage {Math.round((a.analysis_quality.pose.critical_joint_coverage ?? 0) * 100)}%
              </Text>
              <Text style={s.note}>
                Score confidence: {(a.analysis_quality.score_confidence ?? "unknown").toUpperCase()} ·
                {a.analysis_quality.assessable_steps ?? 0}/27 steps assessable
              </Text>
              <Text style={s.note}>
                Subject tracking: {(a.analysis_quality.pose.subject_selection_confidence ?? "unknown").toUpperCase()} confidence ·
                {a.analysis_quality.pose.competing_tracks ?? 0} competing person track(s)
              </Text>
              {a.analysis_quality.pose.joint_visibility ? (
                <Text style={s.note}>
                  Joint visibility in observed frames: {["left_wrist", "right_wrist", "left_knee", "right_knee", "left_ankle", "right_ankle"]
                    .filter((key) => a.analysis_quality?.pose?.joint_visibility?.[key])
                    .map((key) => {
                      const joint = a.analysis_quality?.pose?.joint_visibility?.[key];
                      return `${key.replace("_", " ")} ${Math.round((joint?.coverage ?? 0) * 100)}%`;
                    }).join(" · ")}
                </Text>
              ) : null}
              {a.analysis_quality.pose.interpolated_frames ? (
                <Text style={s.note}>
                  {a.analysis_quality.pose.interpolated_frames} interpolated frames were shown for continuity but excluded from measurements.
                </Text>
              ) : null}
              {Object.keys(a.analysis_quality.event_methods ?? {}).length ? (
                <Text style={s.note}>
                  Event timing methods: {Object.entries(a.analysis_quality.event_methods ?? {})
                    .map(([key, method]) => `${key.replace("_", " ")}: ${method.replaceAll("_", " ")}`).join(" · ")}
                </Text>
              ) : null}
              {a.analysis_quality.event_timing ? (
                <Text style={s.note}>
                  Event timing confidence: {(a.analysis_quality.event_timing.overall ?? "unavailable").toUpperCase()}
                  {Object.entries(a.analysis_quality.event_timing.events ?? {}).length
                    ? ` · ${Object.entries(a.analysis_quality.event_timing.events ?? {}).map(([key, value]) => `${key.toUpperCase()}: ${value}`).join(" · ")}`
                    : ""}
                  . This rates timing evidence, not the bowler's technique.
                </Text>
              ) : null}
              {Object.keys(a.analysis_quality.joint_confidence ?? {}).length ? (
                <Text style={s.note}>
                  Keypoint visibility at detected events: {Object.entries(a.analysis_quality.joint_confidence ?? {})
                    .map(([key, value]) => `${key.replace("_", " ")}: ${typeof value === "number" ? `${Math.round(value * 100)}%` : "unavailable"}`).join(" · ")}
                  . This is pose-joint visibility confidence, not confidence that the event timing itself is correct.
                </Text>
              ) : null}
              {Object.keys(a.analysis_quality.contact_evidence ?? {}).length ? (
                <Text style={s.note}>
                  Foot-contact support: {Object.entries(a.analysis_quality.contact_evidence ?? {})
                    .map(([key, value]) => `${key.toUpperCase()}: ${value.observed_frames ?? 0} observed frames across ${value.plateau_duration_s ?? 0}s`).join(" · ")}
                  . Contact timing is a pose-based heuristic, not direct impact detection.
                </Text>
              ) : null}
              {a.video_meta?.quality ? (
                <>
                  <Text style={s.note}>
                    Capture screening: {(a.video_meta.quality.rating ?? "unknown").toUpperCase()}
                    {a.video_meta.quality.flags?.length ? ` · ${a.video_meta.quality.flags.map((flag) => flag.replaceAll("_", " ")).join(" · ")}` : " · no screening flags"}
                  </Text>
                  <Text style={s.note}>Capture flags are screening heuristics, not a calibrated video-quality score.</Text>
                </>
              ) : null}
              <Text style={s.note}>Overall and phase scores are equal-weight averages of assessable movement-step scores; unassessable steps are excluded.</Text>
              <Text style={s.note}>Single-camera 2D coaching estimates only. These are not 3D biomechanical measurements or medical assessments.</Text>
              <Text style={s.note}>
                {a.analysis_quality.release_evidence?.ball_separation_visible
                  ? `Ball separation visually identified by AI · AI-reported ${a.analysis_quality.release_evidence.confidence ?? "low"} confidence · not sensor-confirmed.`
                  : "Ball separation was not clearly visible; actual ball release is unconfirmed. A wrist-apex proxy is not a confirmed release."}
              </Text>
            </View>
          ) : null}
          {a.video_path ? (
            <View style={{ gap: space.md }}>
              <SkeletonPlayer
                analysisId={a.id}
                meta={a.video_meta ?? {}}
                steps={steps}
                pose={pose.data}
                bowlingArm={profile.data?.bowling_arm ?? "Right"}
                selected={selected}
                seekNonce={seekNonce}
                onSelect={(i) => selectStep(i)}
              />
              {selected != null && steps[selected] ? <StepCard step={steps[selected]} index={selected} /> : steps.length ? (
                <Text style={s.note}>Tap a marker on the timeline or a step below to freeze the video at that moment.</Text>
              ) : null}
            </View>
          ) : null}

          <Animated.View entering={FadeInDown} style={s.scoreCard}>
            <Text style={s.kicker}>OVERALL SCORE</Text>
            <View style={{ flexDirection: "row", alignItems: "flex-end" }}>
              <Text style={[s.bigScore, { color: scoreColor(a.overall_score, colors) }]} testID="report-overall-score">{a.overall_score_assessable === false ? "—" : a.overall_score.toFixed(1)}</Text>
              <Text style={s.outOf}>/10</Text>
            </View>
            <View style={{ flexDirection: "row", gap: space.sm, flexWrap: "wrap" }}>
              {a.action_type ? <Pill testID="report-action-type" label={`${a.action_type} action`} color={colors.onSurface} icon="body" /> : null}
              <Pill testID="report-camera-view" label={`Camera: ${(a.camera_view ?? "unknown").replace("_", " ")} · ${a.camera_view_confidence ?? "low"} confidence`} color={colors.muted} icon="camera" />
              <Pill label={new Date(a.created_at).toLocaleDateString()} color={colors.muted} icon="calendar" />
            </View>
            <Text style={s.summary} testID="report-summary">{a.summary}</Text>
            {a.overall_score_assessable === false ? <Text style={s.note}>Not enough clear, assessable movement to provide a reliable overall score.</Text> : null}
          </Animated.View>

          {a.is_bowling_video ? (
            <>
              <View style={{ flexDirection: "row", gap: space.md }}>
                <View style={[s.metric, { flex: 1 }]} testID="report-pace-band">
                  <Text style={s.kicker}>BOWLING SPEED</Text>
                  <Text style={s.metricValue}>{min && max ? `${min}-${max}` : "—"}</Text>
                  <Text style={s.metricSub}>{min && max ? `${a.pace_band?.label ?? "Estimated"} km/h` : "Unavailable without calibrated radar or ball tracking"}</Text>
                  <View style={s.gauge}>
                    {min && max ? <View style={[s.gaugeFill, { left: pct(min), right: `${100 - parseFloat(pct(max))}%` }]} /> : null}
                  </View>
                  <View style={s.gaugeLabels}>
                    <Text style={s.gaugeLabel}>90</Text>
                    <Text style={s.gaugeLabel}>160</Text>
                  </View>
                </View>
                <View style={[s.metric, { flex: 1, borderColor: riskColor(a.injury_risk?.level, colors) }]} testID="report-injury-risk">
                  <Text style={s.kicker}>INJURY RISK</Text>
                  <Text style={[s.metricValue, { color: a.injury_risk?.level === "not_assessed" ? colors.muted : riskColor(a.injury_risk?.level, colors), textTransform: "uppercase" }]}>{a.injury_risk?.level === "not_assessed" ? "Not assessed" : (a.injury_risk?.level ?? "—")}</Text>
                  <Text style={s.metricSub}>{a.injury_risk?.mixed_action == null ? "Not assessed from one 2D video" : a.injury_risk.mixed_action ? "Mixed action detected" : "No mixed action"}</Text>
                  <Text style={s.metricSub}>Counter-rotation: {a.injury_risk?.counter_rotation === "not_assessed" ? "Not assessed from this view" : (a.injury_risk?.counter_rotation ?? "—")}</Text>
                </View>
              </View>
              {a.injury_risk?.notes ? <Text style={s.note}>{a.injury_risk.notes}</Text> : null}
              {a.injury_risk?.areas?.length ? <InjuryScanner areas={a.injury_risk.areas} /> : null}

              <View>
                <SectionTitle title="Phase Breakdown" />
                <View style={s.grid}>
                  {a.phases.map((p) => (
                    <View key={p.key} style={s.phase} testID={`phase-card-${p.key}`}>
                      <View style={s.phaseHead}>
                        <Text style={s.phaseName}>{p.name || phaseLabel(p.key)}</Text>
                        <Text style={[s.phaseScore, { color: p.assessable === false ? colors.muted : scoreColor(p.score, colors) }]}>{p.assessable === false ? "—" : Number(p.score).toFixed(1)}</Text>
                      </View>
                      <View style={s.track}>
                        {p.assessable === false ? null : <View style={[s.fill, { width: `${p.score * 10}%`, backgroundColor: scoreColor(p.score, colors) }]} />}
                      </View>
                      <Text style={s.phaseFeedback}>{p.feedback}</Text>
                    </View>
                  ))}
                </View>
              </View>

              {steps.length ? <StepList steps={steps} selected={selected} onSelect={(i) => selectStep(i, true)} /> : null}

              {coachingPriorities.length ? (
                <View>
                  <SectionTitle title="Priority Coaching Focus" />
                  <Text style={s.body}>Start with these changes in order. PACED keeps the focus on the two most actionable findings.</Text>
                  <View style={{ gap: space.sm }}>
                    {coachingPriorities.map((item) => (
                      <PressScale
                        key={item.step_key || item.priority}
                        style={[s.fault, { borderLeftColor: item.type === "fault" && item.severity ? riskColor(item.severity, colors) : colors.accent }]}
                        testID={`coaching-priority-${item.priority}`}
                        onPress={() => {
                          const targetIndex = steps.findIndex((step) => step.key === item.step_key && step.status !== "not_visible" && step.t != null);
                          if (targetIndex >= 0) selectStep(targetIndex, true);
                        }}
                      >
                        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: space.sm }}>
                          <Text style={s.faultTitle}>{item.priority}. {item.title}</Text>
                          <Pill
                            label={item.type === "fault" ? `${item.severity ?? "technical"} fault` : "Optional improvement"}
                            color={item.type === "fault" && item.severity ? riskColor(item.severity, colors) : colors.accent}
                          />
                        </View>
                        <Text style={s.faultPhase}>{phaseLabel(item.phase)}</Text>
                        <Text style={s.body}>{item.reason}</Text>
                        {item.action ? (
                          <View style={s.fixRow}>
                            <Ionicons name="construct" size={14} color={colors.accent} />
                            <Text style={[s.body, { flex: 1, color: colors.onSurface }]}>{item.action}</Text>
                          </View>
                        ) : null}
                      </PressScale>
                    ))}
                  </View>
                </View>
              ) : null}

              {a.strengths.length ? (
                <View>
                  <SectionTitle title="Strengths" />
                  {a.strengths.map((t, i) => (
                    <View key={i} style={s.listRow}>
                      <Ionicons name="checkmark-circle" size={18} color={colors.success} />
                      <Text style={s.listText}>{t}</Text>
                    </View>
                  ))}
                </View>
              ) : null}

              {a.tips.length ? (
                <View>
                  <SectionTitle title="Coach Tips" />
                  {a.tips.map((t, i) => (
                    <View key={i} style={s.listRow}>
                      <Text style={s.tipNum}>{i + 1}</Text>
                      <Text style={s.listText}>{t}</Text>
                    </View>
                  ))}
                </View>
              ) : null}
            </>
          ) : null}

          <PrimaryButton testID="report-compare-button" label="Compare with another delivery" icon="git-compare" variant="secondary" onPress={() => router.push("/compare")} />
          <PrimaryButton testID="report-ask-coach-button" label="Ask AI Assistant about this" icon="chatbubbles" onPress={() => router.push("/coach")} />
        </ScrollView>
      )}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: space.lg, paddingBottom: space.sm, borderBottomWidth: 1, borderBottomColor: c.divider },
  headerTitle: { fontFamily: fonts.display, fontSize: 15, color: c.onSurface, textTransform: "uppercase", letterSpacing: 2.5 },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  confirm: { padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.error, gap: space.md },
  confirmText: { fontFamily: fonts.textBold, fontSize: 15, color: c.onSurface },
  smallBtn: { minHeight: 44, paddingHorizontal: space.xl, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  smallBtnText: { fontFamily: fonts.textBold, fontSize: 14, color: c.onSurface },
  qualityCard: { padding: space.md, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.xs },
  scoreCard: { padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.md },
  kicker: { fontFamily: fonts.textXBold, fontSize: 11, color: c.muted, letterSpacing: 1.5 },
  bigScore: { fontFamily: fonts.displaySemi, fontSize: 80, lineHeight: 88, letterSpacing: -2 },
  outOf: { fontFamily: fonts.displaySemi, fontSize: 30, color: c.muted, marginBottom: 12, marginLeft: 4 },
  summary: { fontFamily: fonts.text, fontSize: 14, lineHeight: 21, color: c.onSurfaceSecondary },
  metric: { padding: space.md, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: 4 },
  metricValue: { fontFamily: fonts.display, fontSize: 30, color: c.onSurface },
  metricSub: { fontFamily: fonts.text, fontSize: 12, color: c.muted },
  gauge: { height: 8, borderRadius: 4, backgroundColor: c.surfaceTertiary, marginTop: space.sm, overflow: "hidden" },
  gaugeFill: { position: "absolute", top: 0, bottom: 0, backgroundColor: c.brandPrimary, borderRadius: 4 },
  gaugeLabels: { flexDirection: "row", justifyContent: "space-between" },
  gaugeLabel: { fontFamily: fonts.text, fontSize: 10, color: c.muted },
  note: { fontFamily: fonts.text, fontSize: 13, lineHeight: 19, color: c.onSurfaceTertiary, marginTop: -space.md },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  phase: { width: "48.5%", padding: space.md, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.sm },
  phaseHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  phaseName: { flex: 1, fontFamily: fonts.textBold, fontSize: 13, color: c.onSurface },
  phaseScore: { fontFamily: fonts.display, fontSize: 24 },
  track: { height: 4, borderRadius: 2, backgroundColor: c.surfaceTertiary, overflow: "hidden" },
  fill: { height: 4, borderRadius: 2 },
  phaseFeedback: { fontFamily: fonts.text, fontSize: 12, lineHeight: 17, color: c.muted },
  fault: { padding: space.md, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, borderLeftWidth: 3, gap: 6 },
  faultTitle: { flex: 1, fontFamily: fonts.textXBold, fontSize: 15, color: c.onSurface },
  faultPhase: { fontFamily: fonts.textBold, fontSize: 12, color: c.accent },
  body: { fontFamily: fonts.text, fontSize: 13, lineHeight: 19, color: c.onSurfaceTertiary },
  fixRow: { flexDirection: "row", gap: space.sm, alignItems: "flex-start", paddingTop: 4 },
  listRow: { flexDirection: "row", gap: space.md, alignItems: "flex-start", marginBottom: space.sm },
  listText: { flex: 1, fontFamily: fonts.text, fontSize: 14, lineHeight: 20, color: c.onSurfaceSecondary },
  tipNum: { width: 22, height: 22, borderRadius: 11, textAlign: "center", lineHeight: 22, fontFamily: fonts.textXBold, fontSize: 12, color: c.onBrandPrimary, backgroundColor: c.brandPrimary, overflow: "hidden" },
}));
