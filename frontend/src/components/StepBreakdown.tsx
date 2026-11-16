import { Pressable, Text, View } from "react-native";

import type { Step } from "@/src/api";
import { PHASES, fonts, radius, space } from "@/src/constants";
import { Pill, SectionTitle, scoreColor } from "@/src/components/ui";
import { makeStyles, useTheme } from "@/src/theme";

const STATUS_LABEL: Record<string, string> = { good: "Good", ok: "Work on", fault: "Fault", not_visible: "Not visible" };
const METRIC_LABEL: Record<string, string> = { front_knee: "Front knee", back_knee: "Back knee", bowling_elbow: "Bowling elbow", trunk_lean: "Trunk lean" };

function useStatusColor() {
  const { colors } = useTheme();
  return (status: string) =>
    status === "good" ? colors.success : status === "fault" ? colors.error : status === "ok" ? colors.warning : colors.muted;
}

export function StepCard({ step, index }: { step: Step; index: number }) {
  const s = useStyles();
  const { colors } = useTheme();
  const statusColor = useStatusColor();
  const metrics = Object.entries(step.metrics || {}).filter(([, v]) => v != null && v > 0);
  return (
    <View style={s.card} testID="selected-step-card">
      <View style={s.headRow}>
        <Text style={s.num}>{String(index + 1).padStart(2, "0")}</Text>
        <View style={{ flex: 1 }}>
          <Text style={s.name} testID="selected-step-name">{step.name}</Text>
          <Text style={s.meta}>{PHASES.find((p) => p.key === step.phase)?.label} · {step.t != null ? `${step.t.toFixed(2)}s` : "—"}</Text>
        </View>
        {step.status !== "not_visible" ? <Text style={[s.score, { color: scoreColor(step.score, colors) }]}>{Number(step.score).toFixed(0)}</Text> : null}
      </View>
      <Pill label={STATUS_LABEL[step.status] ?? step.status} color={statusColor(step.status)} />
      <Text style={s.desc}>{step.description}</Text>
      {step.observation ? <Text style={s.body}>{step.observation}</Text> : null}
      {step.cue ? (
        <View style={s.cue}>
          <Text style={s.cueLabel}>CUE</Text>
          <Text style={s.cueText}>{step.cue}</Text>
        </View>
      ) : null}
      {metrics.length ? (
        <View style={s.metrics}>
          {metrics.map(([k, v]) => (
            <View key={k} style={s.metric} testID={`step-metric-${k}`}>
              <Text style={s.metricValue}>{v}°</Text>
              <Text style={s.metricLabel}>{METRIC_LABEL[k] ?? k}</Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

export function StepList({ steps, selected, onSelect }: { steps: Step[]; selected: number | null; onSelect: (i: number) => void }) {
  const s = useStyles();
  const statusColor = useStatusColor();
  return (
    <View>
      <SectionTitle title="27-Step Biomechanics" />
      {PHASES.map((ph) => {
        const items = steps.map((st, i) => ({ st, i })).filter((x) => x.st.phase === ph.key);
        if (!items.length) return null;
        return (
          <View key={ph.key} style={{ marginBottom: space.md }}>
            <Text style={s.group}>{ph.label.toUpperCase()}</Text>
            {items.map(({ st, i }) => (
              <Pressable key={st.key} testID={`step-row-${st.key}`} onPress={() => onSelect(i)} style={[s.row, i === selected && s.rowActive]}>
                <Text style={s.rowNum}>{i + 1}</Text>
                <View style={[s.dot, { backgroundColor: statusColor(st.status) }]} />
                <Text style={s.rowName} numberOfLines={1}>{st.name}</Text>
                <Text style={s.rowTime}>{st.t != null ? `${st.t.toFixed(1)}s` : "—"}</Text>
                <Text style={s.rowScore}>{st.status === "not_visible" ? "–" : Number(st.score).toFixed(0)}</Text>
              </Pressable>
            ))}
          </View>
        );
      })}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  card: { padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.brandPrimary, gap: space.sm },
  headRow: { flexDirection: "row", alignItems: "center", gap: space.md },
  num: { fontFamily: fonts.display, fontSize: 34, color: c.brandPrimary },
  name: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface, textTransform: "uppercase" },
  meta: { fontFamily: fonts.text, fontSize: 12, color: c.muted },
  score: { fontFamily: fonts.display, fontSize: 36 },
  desc: { fontFamily: fonts.text, fontSize: 13, lineHeight: 19, color: c.muted, fontStyle: "italic" },
  body: { fontFamily: fonts.text, fontSize: 14, lineHeight: 21, color: c.onSurfaceSecondary },
  cue: { flexDirection: "row", gap: space.sm, alignItems: "center", padding: space.md, borderRadius: radius.md, backgroundColor: c.brandTertiary },
  cueLabel: { fontFamily: fonts.textXBold, fontSize: 11, color: c.brandPrimary, letterSpacing: 1 },
  cueText: { flex: 1, fontFamily: fonts.textBold, fontSize: 14, color: c.onSurface },
  metrics: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  metric: { paddingHorizontal: space.md, paddingVertical: space.sm, borderRadius: radius.md, backgroundColor: c.surfaceTertiary, minWidth: 84 },
  metricValue: { fontFamily: fonts.display, fontSize: 22, color: c.warning },
  metricLabel: { fontFamily: fonts.text, fontSize: 11, color: c.muted },
  group: { fontFamily: fonts.textXBold, fontSize: 11, color: c.muted, letterSpacing: 1.5, marginBottom: space.xs },
  row: { flexDirection: "row", alignItems: "center", gap: space.sm, minHeight: 44, paddingHorizontal: space.md, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, marginBottom: 4, borderWidth: 1, borderColor: "transparent" },
  rowActive: { borderColor: c.brandPrimary },
  rowNum: { width: 22, fontFamily: fonts.displaySemi, fontSize: 15, color: c.muted },
  dot: { width: 8, height: 8, borderRadius: 4 },
  rowName: { flex: 1, fontFamily: fonts.textBold, fontSize: 13, color: c.onSurface },
  rowTime: { fontFamily: fonts.text, fontSize: 11, color: c.muted, width: 38, textAlign: "right" },
  rowScore: { fontFamily: fonts.display, fontSize: 18, color: c.onSurface, width: 22, textAlign: "right" },
}));
