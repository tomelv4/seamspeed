import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { apiSend, useWorkload, Workload } from "@/src/api";
import { fonts, radius, space } from "@/src/constants";
import { ProLocked } from "@/src/components/ProLocked";
import { Bars, ErrorBanner, Ionicons, Loading, PressScale, PrimaryButton, SectionTitle, riskColor } from "@/src/components/ui";
import { useSubscription } from "@/src/revenuecat";
import { makeStyles, useTheme } from "@/src/theme";

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export default function WorkloadScreen() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { isSubscribed, isLoading: subLoading } = useSubscription();
  const wl = useWorkload();
  const [balls, setBalls] = useState(36);
  const [intensity, setIntensity] = useState(7);
  const [dayOffset, setDayOffset] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const d = wl.data;

  const log = async () => {
    setSaving(true);
    setError(null);
    try {
      const day = new Date();
      day.setDate(day.getDate() - dayOffset);
      const res = await apiSend<Workload>("/workload", "POST", { date: iso(day), balls, intensity });
      qc.setQueryData(["workload"], res);
    } catch (e: any) {
      setError(e?.message ?? "Could not log balls");
    } finally {
      setSaving(false);
    }
  };
  const remove = async (id: string) => {
    setError(null);
    try {
      await apiSend(`/workload/${id}`, "DELETE");
      wl.refetch();
    } catch (e: any) {
      setError(e?.message ?? "Could not delete entry");
    }
  };
  const back = () => (router.canGoBack() ? router.back() : router.replace("/"));
  const acwrPct = d?.acwr != null ? Math.min(100, (d.acwr / 2) * 100) : 0;

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <PressScale testID="workload-back-button" style={s.iconBtn} onPress={back}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </PressScale>
        <Text style={s.headerTitle}>Workload</Text>
        <View style={{ width: 44 }} />
      </View>
      <ScrollView
        contentContainerStyle={{ padding: space.lg, paddingBottom: insets.bottom + space.xl, gap: space.xl }}
        refreshControl={<RefreshControl tintColor={colors.accent} refreshing={wl.isRefetching} onRefresh={() => { wl.refetch(); }} />}
      >
        {!subLoading && !isSubscribed ? (
          <ProLocked testID="workload-locked" title="Workload is Pro" body="Track weekly bowling volume, recovery days and changes against your recent baseline." />
        ) : wl.isLoading ? (
          <Loading />
        ) : wl.isError || !d ? (
          <ErrorBanner testID="workload-error" message="Could not load workload." onRetry={() => wl.refetch()} />
        ) : (
          <>
            <View style={[s.card, { borderColor: riskColor(d.status, colors) }]} testID="workload-status-card">
              <Text style={s.kicker}>WORKLOAD STATUS</Text>
              <Text style={[s.status, { color: riskColor(d.status, colors) }]} testID="workload-status">{d.status === "medium" ? "CAUTION" : d.status.toUpperCase()}</Text>
              <Text style={s.body}>{d.headline}</Text>
              <Text style={s.advice}>{d.advice}</Text>
            </View>

            <View style={s.stats}>
              <View style={s.stat}><Text style={s.statValue} testID="workload-acute">{d.acute}</Text><Text style={s.statLabel}>Balls · 7 days</Text></View>
              <View style={s.stat}><Text style={s.statValue}>{d.rest_days_7}</Text><Text style={s.statLabel}>Rest days</Text></View>
              <View style={s.stat}><Text style={s.statValue} testID="workload-acwr">{d.acwr ?? "—"}</Text><Text style={s.statLabel}>A:C ratio</Text></View>
            </View>

            <View style={s.card}>
              <Text style={s.kicker}>ACUTE : CHRONIC RATIO</Text>
              <View style={s.zoneTrack}>
                <View style={[s.zone, { left: "40%", width: "25%", backgroundColor: colors.brandTertiary }]} />
                {d.acwr != null ? <View style={[s.needle, { left: `${acwrPct}%`, backgroundColor: riskColor(d.status, colors) }]} /> : null}
              </View>
              <View style={s.zoneLabels}><Text style={s.tiny}>0</Text><Text style={s.tiny}>0.8–1.3 reference range</Text><Text style={s.tiny}>2.0</Text></View>
              <Text style={s.tiny}>{d.acwr == null ? "Ratio appears after 3+ weeks of logged bowling." : `This week ${d.acute} vs ${d.chronic_weekly}/week 4-week average. This is a load comparison, not an injury-risk score.`}</Text>
            </View>

            <View style={s.card} testID="workload-weekly-chart">
              <Text style={s.kicker}>WEEKLY BALLS · 8 WEEKS{d.weekly_guide ? ` · GUIDE ${d.weekly_guide}` : ""}</Text>
              <Bars data={d.weeks.map((w) => ({ label: w.label, value: w.balls }))} max={Math.max(d.weekly_guide ?? 0, ...d.weeks.map((w) => w.balls), 1)} color={colors.accent} height={120} />
            </View>

            {d.flags.length ? (
              <View>
                <SectionTitle title="Flags" />
                {d.flags.map((f, i) => (
                  <View key={i} style={[s.flag, { borderLeftColor: riskColor(f.level, colors) }]} testID={`workload-flag-${i}`}>
                    <Text style={s.body}>{f.text}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            <View style={s.card}>
              <Text style={s.kicker}>LOG BOWLING</Text>
              <View style={s.rowCenter}>
                {[["Today", 0], ["Yesterday", 1], ["2 days ago", 2]].map(([label, off]) => (
                  <Pressable key={label} testID={`workload-day-${off}`} onPress={() => setDayOffset(off as number)} style={[s.chip, dayOffset === off && s.chipOn]}>
                    <Text style={[s.chipText, dayOffset === off && { color: colors.onBrandPrimary }]}>{label}</Text>
                  </Pressable>
                ))}
              </View>
              <View style={s.stepper}>
                <Pressable testID="workload-balls-minus" style={s.stepBtn} onPress={() => setBalls((b) => Math.max(6, b - 6))}><Ionicons name="remove" size={20} color={colors.onSurface} /></Pressable>
                <View style={{ alignItems: "center" }}>
                  <Text style={s.stepValue} testID="workload-balls-value">{balls}</Text>
                  <Text style={s.tiny}>balls · {Math.floor(balls / 6)}.{balls % 6} overs</Text>
                </View>
                <Pressable testID="workload-balls-plus" style={s.stepBtn} onPress={() => setBalls((b) => Math.min(300, b + 6))}><Ionicons name="add" size={20} color={colors.onSurface} /></Pressable>
              </View>
              <Text style={s.tiny}>Intensity (effort out of 10)</Text>
              <View style={s.rowCenter}>
                {[5, 6, 7, 8, 9, 10].map((n) => (
                  <Pressable key={n} testID={`workload-intensity-${n}`} onPress={() => setIntensity(n)} style={[s.chip, s.chipSmall, intensity === n && s.chipOn]}>
                    <Text style={[s.chipText, intensity === n && { color: colors.onBrandPrimary }]}>{n}</Text>
                  </Pressable>
                ))}
              </View>
              {error ? <ErrorBanner testID="workload-log-error" message={error} /> : null}
              <PrimaryButton testID="workload-log-button" label="Log Balls" icon="add-circle" loading={saving} onPress={log} />
              <Text style={s.tiny}>Live-session deliveries are counted automatically.</Text>
            </View>

            {d.entries.length ? (
              <View>
                <SectionTitle title="Recent Entries" />
                {d.entries.map((e) => (
                  <View key={e.id} style={s.entry} testID={`workload-entry-${e.id}`}>
                    <Text style={s.entryDate}>{e.date}</Text>
                    <Text style={s.entryBalls}>{e.balls} balls</Text>
                    <Text style={s.tiny}>{e.source === "session" ? "Session" : `RPE ${e.intensity}`}</Text>
                    <Pressable testID={`workload-delete-${e.id}`} hitSlop={10} onPress={() => remove(e.id)} style={s.del}>
                      <Ionicons name="close" size={16} color={colors.muted} />
                    </Pressable>
                  </View>
                ))}
              </View>
            ) : null}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: space.lg, paddingBottom: space.sm, borderBottomWidth: 1, borderBottomColor: c.divider },
  headerTitle: { fontFamily: fonts.display, fontSize: 15, color: c.onSurface, textTransform: "uppercase", letterSpacing: 2.5 },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  card: { padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.md },
  kicker: { fontFamily: fonts.textXBold, fontSize: 11, color: c.muted, letterSpacing: 2 },
  status: { fontFamily: fonts.display, fontSize: 30, letterSpacing: 2 },
  body: { fontFamily: fonts.text, fontSize: 14, lineHeight: 20, color: c.onSurfaceSecondary },
  advice: { fontFamily: fonts.textBold, fontSize: 13, lineHeight: 19, color: c.accent },
  stats: { flexDirection: "row", gap: space.sm },
  stat: { flex: 1, padding: space.md, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  statValue: { fontFamily: fonts.mono, fontSize: 24, color: c.onSurface },
  statLabel: { fontFamily: fonts.text, fontSize: 11, color: c.muted },
  zoneTrack: { height: 10, borderRadius: 5, backgroundColor: c.surfaceTertiary, overflow: "hidden" },
  zone: { position: "absolute", top: 0, bottom: 0 },
  needle: { position: "absolute", top: 0, bottom: 0, width: 4, marginLeft: -2, borderRadius: 2 },
  zoneLabels: { flexDirection: "row", justifyContent: "space-between" },
  tiny: { fontFamily: fonts.text, fontSize: 11, color: c.muted },
  flag: { padding: space.md, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, borderLeftWidth: 3, marginBottom: space.sm },
  rowCenter: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  chip: { height: 40, paddingHorizontal: space.md, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceTertiary, justifyContent: "center" },
  chipSmall: { minWidth: 44, alignItems: "center" },
  chipOn: { backgroundColor: c.brandPrimary, borderColor: c.accentLine },
  chipText: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurfaceTertiary },
  stepper: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  stepBtn: { width: 48, height: 48, borderRadius: radius.md, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  stepValue: { fontFamily: fonts.mono, fontSize: 36, color: c.onSurface },
  entry: { flexDirection: "row", alignItems: "center", gap: space.md, minHeight: 44, paddingHorizontal: space.md, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, marginBottom: 4 },
  entryDate: { fontFamily: fonts.mono, fontSize: 12, color: c.onSurfaceTertiary },
  entryBalls: { flex: 1, fontFamily: fonts.textBold, fontSize: 14, color: c.onSurface },
  del: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
}));
