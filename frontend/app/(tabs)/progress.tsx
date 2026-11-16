import { useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAnalyses, useProgress } from "@/src/api";
import { PHASES, fonts, radius, space } from "@/src/constants";
import { SessionRow } from "@/src/components/SessionRow";
import { Bars, EmptyState, ErrorBanner, Loading, SectionTitle, scoreColor } from "@/src/components/ui";
import { usesNativeTabs } from "@/src/navigation";
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
  const p = progress.data;
  const last = (p?.points ?? []).slice(-8);
  const label = (d: string) => new Date(d).toLocaleDateString(undefined, { day: "numeric", month: "numeric" });

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <Text style={s.title}>Progress</Text>
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
        refreshControl={<RefreshControl tintColor={colors.brandPrimary} refreshing={progress.isRefetching} onRefresh={() => { progress.refetch(); analyses.refetch(); }} />}
      >
        {progress.isLoading ? (
          <Loading testID="progress-loading" />
        ) : progress.isError ? (
          <ErrorBanner testID="progress-error" message="Could not load progress data." onRetry={() => progress.refetch()} />
        ) : !p || p.total === 0 ? (
          <EmptyState testID="progress-empty" icon="trending-up" title="Not enough data yet" body="Analyze a few deliveries and your pace, scores and faults will be charted here." />
        ) : (
          <>
            <View style={s.stats}>
              <View style={s.stat} testID="stat-sessions">
                <Text style={s.statValue}>{p.total}</Text>
                <Text style={s.statLabel}>Deliveries</Text>
              </View>
              <View style={s.stat} testID="stat-best-score">
                <Text style={[s.statValue, { color: colors.brandPrimary }]}>{p.best_score.toFixed(1)}</Text>
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
                  <Text style={s.cardTitle}>Overall score · last {last.length}</Text>
                  <Bars data={last.map((x) => ({ label: label(x.date), value: x.score }))} max={10} color={colors.brandPrimary} format={(v) => v.toFixed(1)} />
                </>
              ) : seg === "pace" ? (
                <>
                  <Text style={s.cardTitle}>Estimated pace (km/h)</Text>
                  <Bars data={last.map((x) => ({ label: label(x.date), value: Math.round(x.pace) }))} max={Math.max(160, ...last.map((x) => x.pace))} color={colors.info} />
                </>
              ) : (
                <>
                  <Text style={s.cardTitle}>Average phase scores</Text>
                  {PHASES.map((ph) => {
                    const v = p.phase_avg[ph.key] ?? 0;
                    return (
                      <View key={ph.key} style={s.phaseRow} testID={`phase-avg-${ph.key}`}>
                        <Text style={s.phaseLabel}>{ph.label}</Text>
                        <View style={s.phaseTrack}>
                          <View style={[s.phaseFill, { width: `${v * 10}%`, backgroundColor: scoreColor(v, colors) }]} />
                        </View>
                        <Text style={s.phaseValue}>{v.toFixed(1)}</Text>
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
                    <View key={f.title} style={[s.faultRow, i > 0 && s.divider]}>
                      <Text style={s.faultTitle} numberOfLines={1}>{f.title}</Text>
                      <Text style={s.faultCount}>×{f.count}</Text>
                    </View>
                  ))}
                </View>
              </View>
            ) : null}

            <View>
              <SectionTitle title="Session History" />
              {(analyses.data ?? []).map((a) => <SessionRow key={a.id} item={a} />)}
            </View>
          </>
        )}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: space.lg, paddingBottom: space.md, gap: space.md, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontFamily: fonts.display, fontSize: 32, color: c.onSurface, textTransform: "uppercase" },
  segment: { flexDirection: "row", backgroundColor: c.surfaceSecondary, borderRadius: radius.pill, padding: 4 },
  segBtn: { flex: 1, height: 36, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  segActive: { backgroundColor: c.brandPrimary },
  segText: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurfaceTertiary },
  stats: { flexDirection: "row", gap: space.sm },
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
  faultCount: { fontFamily: fonts.display, fontSize: 20, color: c.brandPrimary },
}));
