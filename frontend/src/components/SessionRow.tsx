import { useRouter } from "expo-router";
import { Text, View } from "react-native";

import type { Analysis } from "@/src/api";
import { fonts, radius, space } from "@/src/constants";
import { Ionicons, PressScale, riskColor, scoreColor } from "@/src/components/ui";
import { makeStyles, useTheme } from "@/src/theme";

export function SessionRow({ item }: { item: Analysis }) {
  const s = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const date = new Date(item.created_at);
  return (
    <PressScale testID={`session-row-${item.id}`} style={s.row} onPress={() => router.push(`/report/${item.id}`)}>
      <View style={[s.score, { borderColor: item.overall_score_assessable === false ? colors.muted : scoreColor(item.overall_score, colors) }]}>
        <Text style={[s.scoreText, { color: item.overall_score_assessable === false ? colors.muted : scoreColor(item.overall_score, colors) }]}>{item.overall_score_assessable === false ? "—" : item.overall_score.toFixed(1)}</Text>
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={s.title} numberOfLines={1}>
          {item.is_bowling_video ? `${item.action_type || "Delivery"} action` : "Not a bowling clip"}
        </Text>
        <Text style={s.meta}>
          {date.toLocaleDateString(undefined, { day: "numeric", month: "short" })} · {item.pace_band?.label || "—"} · {item.faults.length} faults
        </Text>
      </View>
      <View style={[s.dot, { backgroundColor: item.is_bowling_video && item.injury_risk?.level !== "not_assessed" ? riskColor(item.injury_risk?.level, colors) : colors.muted }]} />
      <Ionicons name="chevron-forward" size={18} color={colors.muted} />
    </PressScale>
  );
}

const useStyles = makeStyles((c) => ({
  row: { flexDirection: "row", alignItems: "center", gap: space.md, padding: space.md, backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: c.border, marginBottom: space.sm },
  score: { width: 52, height: 52, borderRadius: 26, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  scoreText: { fontFamily: fonts.display, fontSize: 22 },
  title: { fontFamily: fonts.textBold, fontSize: 15, color: c.onSurface, textTransform: "capitalize" },
  meta: { fontFamily: fonts.text, fontSize: 12, color: c.muted },
  dot: { width: 8, height: 8, borderRadius: 4 },
}));
