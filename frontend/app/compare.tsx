import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Analysis, useAnalyses, usePose, useProfile } from "@/src/api";
import { fonts, radius, space } from "@/src/constants";
import { ProLocked } from "@/src/components/ProLocked";
import { SkeletonPlayer } from "@/src/components/SkeletonPlayer";
import { EmptyState, Ionicons, Loading, PressScale, SectionTitle, scoreColor } from "@/src/components/ui";
import { useSubscription } from "@/src/revenuecat";
import { makeStyles, useTheme } from "@/src/theme";

const METRICS: [string, string][] = [["front_knee", "Front knee"], ["back_knee", "Back knee"], ["bowling_elbow", "Elbow"], ["trunk_lean", "Trunk lean"]];
const shortDate = (d: string) => new Date(d).toLocaleDateString(undefined, { day: "numeric", month: "short" });

function Side({ a, selected, nonce, arm }: { a: Analysis; selected: number | null; nonce: number; arm: string }) {
  const pose = usePose(a.id, !!a.has_pose);
  return (
    <SkeletonPlayer compact analysisId={a.id} meta={a.video_meta ?? {}} steps={a.steps ?? []} pose={pose.data}
      bowlingArm={arm} selected={selected} seekNonce={nonce} onSelect={() => {}} />
  );
}

export default function Compare() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { isSubscribed, isLoading: subLoading } = useSubscription();
  const analyses = useAnalyses();
  const profile = useProfile();
  const list = (analyses.data ?? []).filter((x) => x.video_path && x.steps?.length);
  const [aId, setAId] = useState<string | null>(null);
  const [bId, setBId] = useState<string | null>(null);
  const [step, setStep] = useState(12);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (list.length >= 2 && !aId && !bId) {
      setAId(list[list.length - 1].id); // oldest
      setBId(list[0].id); // newest
    }
  }, [list, aId, bId]);

  const A = list.find((x) => x.id === aId);
  const B = list.find((x) => x.id === bId);
  const steps = A?.steps ?? [];
  const pick = (i: number) => {
    setStep(i);
    setNonce((n) => n + 1);
  };
  useEffect(() => {
    if (A && B) setNonce((n) => n + 1);
  }, [aId, bId]); // eslint-disable-line react-hooks/exhaustive-deps

  const back = () => (router.canGoBack() ? router.back() : router.replace("/progress"));
  const arm = profile.data?.bowling_arm ?? "Right";
  const pickerProps = { list, colors, s };

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <PressScale testID="compare-back-button" style={s.iconBtn} onPress={back}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </PressScale>
        <Text style={s.headerTitle}>Compare</Text>
        <View style={{ width: 44 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: space.lg, paddingBottom: insets.bottom + space.xl, gap: space.lg }}>
        {!subLoading && !isSubscribed ? (
          <ProLocked testID="compare-locked" title="Compare is Pro" body="Put two deliveries side by side, step by step, to see your action improve." />
        ) : analyses.isLoading ? (
          <Loading />
        ) : list.length < 2 ? (
          <EmptyState testID="compare-empty" icon="git-compare" title="Two analyses needed" body="Analyse at least two deliveries with video to compare them side by side." />
        ) : (
          <>
            <Picker {...pickerProps} label="DELIVERY A" value={aId} other={bId} onPick={setAId} testID="compare-pick-a" />
            <Picker {...pickerProps} label="DELIVERY B" value={bId} other={aId} onPick={setBId} testID="compare-pick-b" />
            {A && B ? (
              <>
                <View style={s.sideRow} testID="compare-players">
                  <View style={s.side}>
                    <Text style={s.sideLabel}>A · {shortDate(A.created_at)}</Text>
                    <Side a={A} selected={step} nonce={nonce} arm={arm} />
                  </View>
                  <View style={s.side}>
                    <Text style={s.sideLabel}>B · {shortDate(B.created_at)}</Text>
                    <Side a={B} selected={step} nonce={nonce} arm={arm} />
                  </View>
                </View>
                <Text style={s.hint}>Solid = bowler · dashed silver = elite reference model</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
                  {steps.map((st, i) => (
                    <Pressable key={st.key} testID={`compare-step-${st.key}`} onPress={() => pick(i)} style={[s.stepChip, i === step && s.chipOn]}>
                      <Text style={[s.chipText, i === step && { color: colors.onBrandPrimary }]}>{i + 1}. {st.name}</Text>
                    </Pressable>
                  ))}
                </ScrollView>

                {steps[step] ? (
                  <View style={s.card} testID="compare-step-card">
                    <Text style={s.stepName}>{steps[step].name}</Text>
                    <View style={s.tableRow}>
                      <Text style={[s.cell, s.cellLabel]}>Score</Text>
                      <Text style={s.cell}>{Number(A.steps![step]?.score ?? 0).toFixed(0)}</Text>
                      <Text style={s.cell}>{Number(B.steps![step]?.score ?? 0).toFixed(0)}</Text>
                      <Delta a={A.steps![step]?.score} b={B.steps![step]?.score} />
                    </View>
                    {METRICS.map(([k, label]) => {
                      const va = (A.steps![step]?.metrics as any)?.[k];
                      const vb = (B.steps![step]?.metrics as any)?.[k];
                      return (
                        <View key={k} style={s.tableRow}>
                          <Text style={[s.cell, s.cellLabel]}>{label}</Text>
                          <Text style={s.cell}>{va ? `${va}°` : "—"}</Text>
                          <Text style={s.cell}>{vb ? `${vb}°` : "—"}</Text>
                          <Delta a={va} b={vb} unit="°" neutral />
                        </View>
                      );
                    })}
                  </View>
                ) : null}

                <View>
                  <SectionTitle title="All 27 Steps" />
                  {steps.map((st, i) => {
                    const sa = Number(A.steps![i]?.score ?? 0), sb = Number(B.steps![i]?.score ?? 0);
                    return (
                      <Pressable key={st.key} onPress={() => pick(i)} style={[s.listRow, i === step && { borderColor: colors.accentLine }]} testID={`compare-row-${st.key}`}>
                        <Text style={s.listNum}>{i + 1}</Text>
                        <Text style={s.listName} numberOfLines={1}>{st.name}</Text>
                        <Text style={[s.listScore, { color: scoreColor(sa, colors) }]}>{sa.toFixed(0)}</Text>
                        <Text style={[s.listScore, { color: scoreColor(sb, colors) }]}>{sb.toFixed(0)}</Text>
                      </Pressable>
                    );
                  })}
                </View>
              </>
            ) : null}
          </>
        )}
      </ScrollView>
    </View>
  );
}

function Picker({ label, value, other, onPick, testID, list, colors, s }: {
  label: string; value: string | null; other: string | null; onPick: (id: string) => void; testID: string;
  list: Analysis[]; colors: ReturnType<typeof useTheme>["colors"]; s: ReturnType<typeof useStyles>;
}) {
  const fmt = (d: string) => `${shortDate(d)} ${new Date(d).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`;
  return (
    <View style={{ gap: space.sm }}>
      <Text style={s.kicker}>{label}</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.sm }}>
        {list.map((x) => {
          const taken = x.id === other;
          return (
            <Pressable key={x.id} testID={`${testID}-${x.id}`} disabled={taken} onPress={() => onPick(x.id)} style={[s.chip, value === x.id && s.chipOn, taken && { opacity: 0.35 }]}>
              <Text style={[s.chipText, value === x.id && { color: colors.onBrandPrimary }]}>{fmt(x.created_at)} · {x.overall_score.toFixed(1)}</Text>
            </Pressable>
          );
        })}
      </ScrollView>
    </View>
  );
}

function Delta({ a, b, unit = "", neutral }: { a?: number; b?: number; unit?: string; neutral?: boolean }) {
  const s = useStyles();
  const { colors } = useTheme();
  if (a == null || b == null || (!a && !b)) return <Text style={s.cell}>—</Text>;
  const d = Math.round((b - a) * 10) / 10;
  const color = neutral || d === 0 ? colors.onSurfaceTertiary : d > 0 ? colors.success : colors.error;
  return <Text style={[s.cell, { color }]}>{d > 0 ? "+" : ""}{d}{unit}</Text>;
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: space.lg, paddingBottom: space.sm, borderBottomWidth: 1, borderBottomColor: c.divider },
  headerTitle: { fontFamily: fonts.display, fontSize: 15, color: c.onSurface, textTransform: "uppercase", letterSpacing: 2.5 },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  kicker: { fontFamily: fonts.textXBold, fontSize: 11, color: c.muted, letterSpacing: 2 },
  chip: { height: 36, flexShrink: 0, paddingHorizontal: space.md, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, justifyContent: "center" },
  stepChip: { height: 36, flexShrink: 0, paddingHorizontal: space.md, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, justifyContent: "center" },
  chipOn: { backgroundColor: c.brandPrimary, borderColor: c.accentLine },
  chipText: { fontFamily: fonts.textBold, fontSize: 12, color: c.onSurfaceTertiary },
  sideRow: { flexDirection: "row", gap: space.sm },
  side: { flex: 1, gap: space.xs },
  sideLabel: { fontFamily: fonts.mono, fontSize: 11, color: c.onSurfaceTertiary },
  hint: { fontFamily: fonts.text, fontSize: 12, color: c.muted },
  card: { padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.sm },
  stepName: { fontFamily: fonts.display, fontSize: 16, color: c.onSurface },
  tableRow: { flexDirection: "row", alignItems: "center", borderTopWidth: 1, borderTopColor: c.divider, paddingTop: space.sm },
  cell: { flex: 1, fontFamily: fonts.mono, fontSize: 14, color: c.onSurface, textAlign: "right" },
  cellLabel: { flex: 1.4, fontFamily: fonts.text, color: c.muted, textAlign: "left" },
  listRow: { flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 44, paddingHorizontal: space.md, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, marginBottom: 4, borderWidth: 1, borderColor: "transparent" },
  listNum: { width: 22, fontFamily: fonts.mono, fontSize: 12, color: c.muted },
  listName: { flex: 1, fontFamily: fonts.textBold, fontSize: 13, color: c.onSurface },
  listScore: { width: 28, textAlign: "right", fontFamily: fonts.mono, fontSize: 14 },
}));
