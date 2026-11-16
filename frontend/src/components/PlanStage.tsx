import { useEffect, useState } from "react";
import { Pressable, Text, View } from "react-native";

import type { PlanItem } from "@/src/api";
import { fonts, radius, space } from "@/src/constants";
import { Ionicons, PrimaryButton } from "@/src/components/ui";
import { makeStyles, useTheme } from "@/src/theme";

function Timer({ minutes, testID }: { minutes: number; testID: string }) {
  const s = useStyles();
  const { colors } = useTheme();
  const [left, setLeft] = useState<number | null>(null);
  useEffect(() => {
    if (left == null || left <= 0) return;
    const t = setTimeout(() => setLeft((v) => (v == null ? v : v - 1)), 1000);
    return () => clearTimeout(t);
  }, [left]);
  const fmt = (n: number) => `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
  return (
    <Pressable testID={testID} onPress={() => setLeft(left == null || left <= 0 ? Math.round(minutes * 60) : null)} style={s.timer}>
      <Ionicons name={left != null && left > 0 ? "stop" : "timer-outline"} size={14} color={colors.accent} />
      <Text style={s.timerText}>{left != null ? fmt(Math.max(0, left)) : `${minutes} min`}</Text>
    </Pressable>
  );
}

export function PlanStage({ title, subtitle, items, onNext, nextLabel, stageKey }: {
  title: string; subtitle: string; items: PlanItem[]; onNext: () => void; nextLabel: string; stageKey: string;
}) {
  const s = useStyles();
  const { colors } = useTheme();
  const [done, setDone] = useState<Record<number, boolean>>({});
  const count = Object.values(done).filter(Boolean).length;
  return (
    <View style={s.card} testID={`plan-stage-${stageKey}`}>
      <View style={s.head}>
        <Text style={s.title}>{title}</Text>
        <Text style={s.count}>{count}/{items.length}</Text>
      </View>
      <Text style={s.sub}>{subtitle}</Text>
      {items.map((it, i) => (
        <View key={i} style={s.item}>
          <Pressable testID={`plan-item-${stageKey}-${i}`} hitSlop={8} onPress={() => setDone((d) => ({ ...d, [i]: !d[i] }))} style={[s.check, done[i] && s.checkOn]}>
            {done[i] ? <Ionicons name="checkmark" size={16} color={colors.onBrandPrimary} /> : null}
          </Pressable>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={[s.itemName, done[i] && { color: colors.muted }]}>{it.name}</Text>
            {it.cue ? <Text style={s.cue}>{it.cue}</Text> : null}
          </View>
          {it.minutes ? <Timer minutes={it.minutes} testID={`plan-timer-${stageKey}-${i}`} /> : it.reps ? <Text style={s.reps}>{it.reps}</Text> : null}
        </View>
      ))}
      <PrimaryButton testID={`plan-next-${stageKey}`} label={nextLabel} icon="arrow-forward" onPress={onNext} />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  card: { padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.md },
  head: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { fontFamily: fonts.display, fontSize: 18, color: c.onSurface, letterSpacing: 0.5 },
  count: { fontFamily: fonts.mono, fontSize: 13, color: c.accent },
  sub: { fontFamily: fonts.text, fontSize: 13, color: c.muted, lineHeight: 19 },
  item: { flexDirection: "row", alignItems: "center", gap: space.md, paddingVertical: space.sm, borderTopWidth: 1, borderTopColor: c.divider },
  check: { width: 28, height: 28, borderRadius: radius.sm, borderWidth: 1.5, borderColor: c.borderStrong, alignItems: "center", justifyContent: "center" },
  checkOn: { backgroundColor: c.brandPrimary, borderColor: c.accentLine },
  itemName: { fontFamily: fonts.textBold, fontSize: 14, color: c.onSurface },
  cue: { fontFamily: fonts.text, fontSize: 12, color: c.muted, lineHeight: 17 },
  reps: { fontFamily: fonts.mono, fontSize: 12, color: c.accent },
  timer: { flexDirection: "row", alignItems: "center", gap: 4, height: 44, paddingHorizontal: space.sm, borderRadius: radius.md, borderWidth: 1, borderColor: c.accentLine },
  timerText: { fontFamily: fonts.mono, fontSize: 12, color: c.accent },
}));
