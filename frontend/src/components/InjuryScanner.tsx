import { useState } from "react";
import { Pressable, Text, View } from "react-native";

import type { InjuryArea } from "@/src/api";
import { fonts, radius, space } from "@/src/constants";
import { Ionicons, SectionTitle, riskColor } from "@/src/components/ui";
import { makeStyles, useTheme } from "@/src/theme";

const AREAS: Record<string, { name: string; detail: string; icon: string }> = {
  lumbar_spine: { name: "Lumbar Spine", detail: "Stress fractures (spondylolysis) from extension + side-bend + twist under load. Highest risk in mixed actions and bowlers under 22.", icon: "git-commit" },
  side_strain: { name: "Abdominal Side Strain", detail: "Oblique tears on the non-bowling side from violent torso stretch and snap at delivery.", icon: "resize" },
  front_leg: { name: "Front-Leg Overload", detail: "Patellar tendinopathy, tibial stress fractures and ankle impingement from 5–9x bodyweight at FFC.", icon: "footsteps" },
  shoulder: { name: "Shoulder & Rotator Cuff", detail: "Posterior shoulder tendinopathy and impingement from braking the arm in follow-through.", icon: "sync" },
  hamstring_groin: { name: "Hamstring & Groin", detail: "Soft-tissue strains from high-speed run-ups and over-striding at the crease.", icon: "flash" },
  workload: { name: "Workload Spikes", detail: "Sudden jumps in weekly balls without recovery days — the leading non-mechanical trigger for bone and tendon injury.", icon: "calendar" },
};

export function InjuryScanner({ areas }: { areas: InjuryArea[] }) {
  const s = useStyles();
  const { colors } = useTheme();
  const [open, setOpen] = useState<string | null>(null);
  const order = Object.keys(AREAS);
  const sorted = [...areas].sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
  return (
    <View testID="injury-scanner">
      <SectionTitle title="Injury Scanner" />
      <View style={s.card}>
        {sorted.map((a, i) => {
          const meta = AREAS[a.key] ?? { name: a.key, detail: "", icon: "alert" };
          const color = riskColor(a.level, colors);
          const expanded = open === a.key;
          return (
            <Pressable key={a.key} testID={`injury-area-${a.key}`} onPress={() => setOpen(expanded ? null : a.key)} style={[s.row, i > 0 && s.divider]}>
              <View style={s.head}>
                <Ionicons name={meta.icon as any} size={16} color={color} />
                <Text style={s.name}>{meta.name}</Text>
                <Text style={[s.level, { color }]}>{(a.level || "low").toUpperCase()}</Text>
              </View>
              <View style={s.track}>
                <View style={[s.fill, { width: `${Math.max(4, Math.min(100, Number(a.score) || 0))}%`, backgroundColor: color }]} />
              </View>
              {expanded ? (
                <View style={{ gap: space.sm, marginTop: space.sm }}>
                  <Text style={s.detail}>{meta.detail}</Text>
                  {a.drivers ? <Text style={s.body}><Text style={s.label}>IN THIS DELIVERY  </Text>{a.drivers}</Text> : null}
                  {a.prevention ? <Text style={s.body}><Text style={s.label}>PREVENTION  </Text>{a.prevention}</Text> : null}
                </View>
              ) : null}
            </Pressable>
          );
        })}
      </View>
      <Text style={s.disclaimer}>Screening guidance only — not a medical diagnosis. See a physio for any pain.</Text>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  card: { borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, paddingHorizontal: space.lg },
  row: { paddingVertical: space.md, minHeight: 44 },
  divider: { borderTopWidth: 1, borderTopColor: c.divider },
  head: { flexDirection: "row", alignItems: "center", gap: space.sm, marginBottom: space.sm },
  name: { flex: 1, fontFamily: fonts.textBold, fontSize: 14, color: c.onSurface },
  level: { fontFamily: fonts.mono, fontSize: 11, letterSpacing: 1 },
  track: { height: 4, borderRadius: 2, backgroundColor: c.surfaceTertiary, overflow: "hidden" },
  fill: { height: 4, borderRadius: 2 },
  detail: { fontFamily: fonts.text, fontSize: 12, lineHeight: 18, color: c.muted },
  body: { fontFamily: fonts.text, fontSize: 13, lineHeight: 19, color: c.onSurfaceSecondary },
  label: { fontFamily: fonts.textXBold, fontSize: 10, color: c.accent, letterSpacing: 1.5 },
  disclaimer: { fontFamily: fonts.text, fontSize: 11, color: c.muted, marginTop: space.sm },
}));
