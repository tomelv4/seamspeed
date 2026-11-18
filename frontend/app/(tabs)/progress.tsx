import { useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAnalyses, useProgress } from "@/src/api";
import { PHASES, fonts, radius, space } from "@/src/constants";
import { SessionRow } from "@/src/components/SessionRow";
import { Bars, EmptyState, ErrorBanner, Ionicons, Loading, SectionTitle, scoreColor } from "@/src/components/ui";
import { usesNativeTabs } from "@/src/navigation";
import { ProLocked } from "@/src/components/ProLocked";
import { useRequirePro, useSubscription } from "@/src/revenuecat";
import { useRouter } from "expo-router";
import { makeStyles, useTheme } from "@/src/theme";

const SEGMENTS = [
  { key: "score", label: "Score" },
  { key: "pace", label: "Pace" },
  { key: "phases", label: "Phases" },
] as const;

export default function ProgressScreen() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const [seg, setSeg] = useState<(typeof SEGMENTS)[number]["key"]>("score");
  const progress = useProgress();
  const analyses = useAnalyses();
  const { isSubscribed } = useSubscription();
  const requirePro = useRequirePro();
  const router = useRouter();
  const p = progress.data;
  const overview = p?.development_overview;
  const hasDevelopmentData = !!overview && (
    overview.bowling.deliveries > 0 || overview.gym.sessions > 0 || overview.recovery.sessions > 0 ||
    overview.practice.drill_completions > 0 || overview.video.analyses > 0
  );
  const last = (p?.points ?? []).slice(-8);
  const scorePoints = last.filter((point) => point.score != null);
  const pacePoints = last.filter((point) => point.pace > 0);
  const label = (d: string) => new Date(d).toLocaleDateString(undefined, { day: "numeric", month: "numeric" });

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
          <Text style={s.title}>Progress</Text>
          <Pressable testID="progress-compare-button" onPress={() => requirePro(() => router.push("/compare"))} style={s.compareBtn}>
            <Ionicons name="git-compare" size={16} color={colors.accent} />
            <Text style={s.compareText}>Compare</Text>
          </Pressable>
        </View>
        <View style={s.segment}>
          {SEGMENTS.map((x) => (
            <Pressable key={x.key} testID={`progress-segment-${x.key}`} onPress={() => setSeg(x.key)} style={[s.segBtn, seg === x.key && s.segActive]}>
              <Text style={[s.segText, seg === x.key && { color: colors.onBrandPrimary }]}>{x.label}</Text>
            </Pressable>
          ))}
        </View>
      </View>
      <ScrollView
        contentContainerStyle={{ padding: space.lg, paddingBottom: bottomChrome + space.xl, gap: space.xl }}
        refreshControl={<RefreshControl tintColor={colors.accent} refreshing={progress.isRefetching} onRefresh={() => { progress.refetch(); analyses.refetch(); }} />}
      >
        {!isSubscribed ? (
          <ProLocked testID="progress-locked" title="Progress is Pro" body="Track scores, phase averages and recurring technique faults over time." />
        ) : progress.isLoading ? (
          <Loading testID="progress-loading" />
        ) : progress.isError ? (
          <ErrorBanner testID="progress-error" message="Could not load progress data." onRetry={() => progress.refetch()} />
        ) : !p || (p.total === 0 && !hasDevelopmentData) ? (
          <EmptyState testID="progress-empty" icon="trending-up" title="Not enough data yet" body="Log bowling workload, complete a coached session, practise a targeted drill or analyse a delivery to start building your development history." />
        ) : (
          <>
            {overview ? (
              <View testID="athlete-development-overview" style={{ gap: space.md }}>
                <View style={{ gap: 4 }}>
                  <SectionTitle title="Athlete Development" />
                  <Text style={s.developmentSubtext}>Your logged training and technique activity · last {overview.window_days} days</Text>
                </View>
                <View style={s.developmentGrid}>
                  <View style={s.developmentStat}>
                    <Text style={s.developmentValue}>{overview.bowling.deliveries.toLocaleString()}</Text>
                    <Text style={s.statLabel}>Bowling deliveries</Text>
                    <Text style={s.developmentHint}>{overview.bowling.logged_days} logged days</Text>
                  </View>
                  <View style={s.developmentStat}>
                    <Text style={s.developmentValue}>{overview.gym.sessions}</Text>
                    <Text style={s.statLabel}>Gym sessions</Text>
                    <Text style={s.developmentHint}>{overview.gym.activities_completed} activities · {overview.gym.actual_sets} sets logged</Text>
                  </View>
                  <View style={s.developmentStat}>
                    <Text style={s.developmentValue}>{overview.recovery.sessions}</Text>
                    <Text style={s.statLabel}>Recovery sessions</Text>
                    <Text style={s.developmentHint}>{overview.recovery.activities_completed} activities completed</Text>
                  </View>
                  <View style={s.developmentStat}>
                    <Text style={s.developmentValue}>{overview.practice.drill_completions}</Text>
                    <Text style={s.statLabel}>Targeted practices</Text>
                    <Text style={s.developmentHint}>{overview.practice.recent_focuses.slice(0, 2).join(" · ") || "No focus logged yet"}</Text>
                  </View>
                  <View style={s.developmentStat}>
                    <Text style={s.developmentValue}>{overview.video.analyses}</Text>
                    <Text style={s.statLabel}>Video analyses</Text>
                    <Text style={s.developmentHint}>{p?.step_trends?.length ?? 0} comparable movement trends</Text>
                  </View>
                </View>
                <View style={s.card}>
                  <Text style={s.cardTitle}>Development activity</Text>
                  {overview.recent_activity.length ? overview.recent_activity.slice(0, 6).map((item, index) => (
                    <View key={item.kind + item.date + index} style={[s.activityRow, index > 0 && s.divider]}>
                      <View style={[s.activityDot, { backgroundColor: item.kind === "video" ? colors.info : item.kind === "practice" ? colors.accent : colors.muted }]} />
                      <View style={{ flex: 1, gap: 2 }}>
                        <Text style={s.faultTitle}>{item.title}</Text>
                        <Text style={s.activityDetail}>{item.detail}</Text>
                      </View>
                      <Text style={s.activityDate}>{new Date(item.date).toLocaleDateString(undefined, { day: "numeric", month: "short" })}</Text>
                    </View>
                  )) : (
                    <Text style={s.developmentSubtext}>Your completed sessions and logged activity will appear here.</Text>
                  )}
                </View>
                <Text style={s.developmentDisclaimer}>Only recorded activity is counted. Planned exercises are not treated as completed, and these separate measures are not combined into a single performance score.</Text>
              </View>
            ) : null}
            {p.total > 0 ? (
            <>
            <View style={s.stats}>
              <View style={s.stat} testID="stat-sessions">
                <Text style={s.statValue}>{p.total}</Text>
                <Text style={s.statLabel}>Video analyses</Text>
              </View>
              <View style={s.stat} testID="stat-best-score">
                <Text style={[s.statValue, { color: colors.accent }]}>{p.best_score > 0 ? p.best_score.toFixed(1) : "—"}</Text>
                <Text style={s.statLabel}>Best score</Text>
              </View>
              <View style={s.stat} testID="stat-best-pace">
                <Text style={s.statValue}>{Math.round(p.best_pace) || "—"}</Text>
                <Text style={s.statLabel}>Top km/h</Text>
              </View>
            </View>

            <View style={s.card} testID="progress-chart">
              {seg === "score" ? (
                <>
                  <Text style={s.cardTitle}>Overall score · last {scorePoints.length} assessable</Text>
                  {scorePoints.length ? (
                    <Bars data={scorePoints.map((x) => ({ label: label(x.date), value: x.score as number }))} max={10} color={colors.accent} format={(v) => v.toFixed(1)} />
                  ) : <Text style={s.phaseLabel}>No reliable scores yet. Clearer footage is needed before a score can be shown.</Text>}
                </>
              ) : seg === "pace" ? (
                <>
                  <Text style={s.cardTitle}>Measured pace (km/h)</Text>
                  {pacePoints.length ? (
                    <Bars data={pacePoints.map((x) => ({ label: label(x.date), value: Math.round(x.pace) }))} max={Math.max(160, ...pacePoints.map((x) => x.pace))} color={colors.info} />
                  ) : <Text style={s.phaseLabel}>Pace data is unavailable until a calibrated radar or ball-tracking source is connected.</Text>}
                </>
              ) : (
                <>
                  <Text style={s.cardTitle}>Average phase scores</Text>
                  {PHASES.map((ph) => {
                    const v = p.phase_avg[ph.key];
                    return (
                      <View key={ph.key} style={s.phaseRow} testID={`phase-avg-${ph.key}`}>
                        <Text style={s.phaseLabel}>{ph.label}</Text>
                        <View style={s.phaseTrack}>
                          {v == null ? null : <View style={[s.phaseFill, { width: `${v * 10}%`, backgroundColor: scoreColor(v, colors) }]} />}
                        </View>
                        <Text style={s.phaseValue}>{v == null ? "—" : v.toFixed(1)}</Text>
                      </View>
                    );
                  })}
                </>
              )}
            </View>

            {p.top_faults.length ? (
              <View>
                <SectionTitle title="Recurring Faults" />
                <View style={s.card}>
                  {p.top_faults.map((f, i) => (
                    <View key={`${f.step_key}-${f.camera_view ?? "unknown"}`} style={[s.faultRow, i > 0 && s.divider]}>
                      <View style={{ flex: 1, gap: 3 }}>
                        <Text style={s.faultTitle} numberOfLines={1}>{f.title}</Text>
                        <Text style={s.phaseLabel}>{f.camera_view?.replace("_", " ") ?? "Camera view unavailable"} · last observed {f.last_seen ? new Date(f.last_seen).toLocaleDateString() : "date unavailable"}</Text>
                      </View>
                      <Text style={s.faultCount}>×{f.count}</Text>
                    </View>
                  ))}
                </View>
              </View>
            ) : null}

            {(p.top_faults.length > 0 || (p.step_trends ?? []).some((trend) => trend.direction === "declined")) ? (
              <View testID="development-review-priorities">
                <SectionTitle title="What to Review Next" />
                <View style={s.card}>
                  {p.top_faults.slice(0, 2).map((fault, index) => (
                    <View key={"fault-" + fault.step_key + "-" + (fault.camera_view ?? "unknown")} style={[s.reviewRow, index > 0 && s.divider]}>
                      <View style={{ flex: 1, gap: 3 }}>
                        <Text style={s.faultTitle}>{fault.title}</Text>
                        <Text style={s.developmentSubtext}>Observed in {fault.count} comparable analysis{fault.count === 1 ? "" : "es"} · last seen {fault.last_seen ? new Date(fault.last_seen).toLocaleDateString() : "date unavailable"}</Text>
                      </View>
                      <Text style={s.reviewLabel}>REVIEW</Text>
                    </View>
                  ))}
                  {(p.step_trends ?? []).filter((trend) => trend.direction === "declined").slice(0, 2).map((trend, index) => (
                    <Pressable key={"decline-" + trend.step_key} onPress={() => router.push("/report/" + trend.current_analysis_id)} style={[s.reviewRow, (p.top_faults.length > 0 || index > 0) && s.divider]}>
                      <View style={{ flex: 1, gap: 3 }}>
                        <Text style={s.faultTitle}>{trend.name}</Text>
                        <Text style={s.developmentSubtext}>Comparable score moved {trend.delta.toFixed(1)} · {trend.camera_view.replace("_", " ")} view</Text>
                      </View>
                      <Text style={[s.reviewLabel, { color: colors.warning }]}>RECHECK</Text>
                      <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                    </Pressable>
                  ))}
                  <Text style={s.developmentDisclaimer}>These are prompts to review the footage, not automatic diagnoses or instructions to change technique. Confirm adjustments with a qualified coach.</Text>
                </View>
              </View>
            ) : null}

            {p.step_trends?.length ? (
              <View testID="technique-trends">
                <SectionTitle title="Technique Trends" />
                <Text style={s.phaseLabel}>Latest comparable observations · same camera view · timestamped evidence</Text>
                <View style={s.card}>
                  {p.step_trends.slice(0, 8).map((trend, i) => {
                    const tint = trend.direction === "improved" ? colors.accent : trend.direction === "declined" ? colors.warning : colors.muted;
                    const change = trend.delta > 0 ? `+${trend.delta.toFixed(1)}` : trend.delta.toFixed(1);
                    return (
                      <Pressable key={trend.step_key} onPress={() => router.push(`/report/${trend.current_analysis_id}`)} style={[s.trendRow, i > 0 && s.divider]} testID={`technique-trend-${trend.step_key}`}>
                        <View style={{ flex: 1, gap: 3 }}>
                          <Text style={s.faultTitle}>{trend.name}</Text>
                          <Text style={s.phaseLabel}>{trend.camera_view.replace("_", " ")} · {new Date(trend.previous_date).toLocaleDateString()} → {new Date(trend.current_date).toLocaleDateString()}</Text>
                          <Text style={s.developmentSubtext}>{(trend.practice_between_count ?? 0) > 0 ? `${trend.practice_between_count} targeted drill${trend.practice_between_count === 1 ? "" : "s"} logged between clips` : "No matching targeted practice logged between clips"}</Text>
                          {(trend.practice_drill_names ?? []).length > 0 ? <Text style={s.developmentHint}>{(trend.practice_drill_names ?? []).join(" · ")}</Text> : null}
                        </View>
                        <View style={{ alignItems: "flex-end", gap: 2 }}>
                          <Text style={[s.trendDelta, { color: tint }]}>{change}</Text>
                          <Text style={s.phaseLabel}>{trend.previous_score.toFixed(1)} → {trend.current_score.toFixed(1)}</Text>
                        </View>
                        <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                      </Pressable>
                    );
                  })}
                </View>
              </View>
            ) : (
              <View testID="technique-trends-empty">
                <SectionTitle title="Technique Trends" />
                <View style={s.card}>
                  <Text style={s.phaseLabel}>Record at least two clear clips from the same camera view to compare individual movements. PACED skips comparisons when event timing, pose evidence or camera-view confidence is insufficient.</Text>
                </View>
              </View>
            )}

            <View>
              <SectionTitle title="Session History" />
              {(analyses.data ?? []).map((a) => <SessionRow key={a.id} item={a} />)}
            </View>
            </>
            ) : (
              <View style={s.card}>
                <Text style={s.cardTitle}>Video technique tracking</Text>
                <Text style={s.phaseLabel}>Analyse a bowling clip to unlock phase scores, comparable movement trends and recurring technique observations.</Text>
              </View>
            )}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: space.lg, paddingBottom: space.md, gap: space.md, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontFamily: fonts.display, fontSize: 24, color: c.onSurface, textTransform: "uppercase", letterSpacing: 2 },
  segment: { flexDirection: "row", backgroundColor: c.surfaceSecondary, borderRadius: radius.pill, padding: 4 },
  compareBtn: { flexDirection: "row", alignItems: "center", gap: 6, height: 40, paddingHorizontal: space.md, borderRadius: radius.md, borderWidth: 1, borderColor: c.accentLine },
  compareText: { fontFamily: fonts.textBold, fontSize: 13, color: c.accent },
  segBtn: { flex: 1, height: 36, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  segActive: { backgroundColor: c.brandPrimary },
  segText: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurfaceTertiary },
  stats: { flexDirection: "row", gap: space.sm },
  developmentGrid: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  developmentStat: { width: "48%", flexGrow: 1, padding: space.md, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: 4 },
  developmentValue: { fontFamily: fonts.display, fontSize: 28, color: c.onSurface },
  developmentHint: { fontFamily: fonts.text, fontSize: 11, color: c.muted },
  developmentSubtext: { fontFamily: fonts.text, fontSize: 12, lineHeight: 17, color: c.onSurfaceSecondary },
  activityDetail: { fontFamily: fonts.text, fontSize: 12, lineHeight: 16, color: c.onSurfaceSecondary, flex: 1 },
  developmentDisclaimer: { fontFamily: fonts.text, fontSize: 11, lineHeight: 16, color: c.muted },
  reviewRow: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingTop: space.sm },
  reviewLabel: { fontFamily: fonts.mono, fontSize: 10, letterSpacing: 1, color: c.accent },
  activityRow: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingTop: space.sm },
  activityDot: { width: 8, height: 8, borderRadius: 4 },
  activityDate: { fontFamily: fonts.mono, fontSize: 11, color: c.muted },
  stat: { flex: 1, padding: space.md, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  statValue: { fontFamily: fonts.display, fontSize: 32, color: c.onSurface },
  statLabel: { fontFamily: fonts.text, fontSize: 12, color: c.muted },
  card: { padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.md, overflow: "hidden" },
  cardTitle: { fontFamily: fonts.textXBold, fontSize: 12, color: c.muted, letterSpacing: 1, textTransform: "uppercase" },
  phaseRow: { flexDirection: "row", alignItems: "center", gap: space.md },
  phaseLabel: { width: 100, fontFamily: fonts.textBold, fontSize: 13, color: c.onSurfaceSecondary },
  phaseTrack: { flex: 1, height: 8, borderRadius: 4, backgroundColor: c.surfaceTertiary, overflow: "hidden" },
  phaseFill: { height: 8, borderRadius: 4 },
  phaseValue: { width: 32, textAlign: "right", fontFamily: fonts.display, fontSize: 18, color: c.onSurface },
  faultRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingTop: space.sm },
  divider: { borderTopWidth: 1, borderTopColor: c.divider },
  faultTitle: { flex: 1, fontFamily: fonts.textBold, fontSize: 14, color: c.onSurface },
  faultCount: { fontFamily: fonts.mono, fontSize: 18, color: c.warning },
  trendRow: { flexDirection: "row", alignItems: "center", gap: space.md, paddingTop: space.sm },
  trendDelta: { fontFamily: fonts.display, fontSize: 22 },
}));
