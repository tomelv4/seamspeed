import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { apiGet, Drill } from "@/src/api";
import { IMAGES, fonts, phaseLabel, radius, space } from "@/src/constants";
import { ErrorBanner, Ionicons, Loading, Pill, PressScale } from "@/src/components/ui";
import { makeStyles, useTheme } from "@/src/theme";

export default function DrillDetail() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const q = useQuery({ queryKey: ["drill", id], queryFn: () => apiGet<Drill>(`/drills/${id}`) });
  const d = q.data;
  const img = IMAGES.drills[(parseInt(String(id).replace(/\D/g, ""), 10) - 1) % IMAGES.drills.length] ?? IMAGES.drills[0];

  return (
    <View style={s.screen}>
      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + space.xl }}>
        <View style={s.hero}>
          <Image source={{ uri: img }} style={s.fill} contentFit="cover" />
          <LinearGradient colors={[colors.scrimLight, colors.surface]} style={s.fill} />
          <PressScale testID="drill-back-button" style={[s.back, { top: insets.top + space.sm }]} onPress={() => (router.canGoBack() ? router.back() : router.replace("/drills"))}>
            <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
          </PressScale>
        </View>
        {q.isLoading ? (
          <Loading />
        ) : !d ? (
          <View style={{ padding: space.lg }}><ErrorBanner testID="drill-error" message="Drill not found." /></View>
        ) : (
          <View style={s.body}>
            <View style={{ flexDirection: "row", gap: space.sm }}>
              <Pill label={phaseLabel(d.phase)} color={colors.accent} />
              <Pill label={d.duration} color={colors.onSurface} icon="time-outline" />
              <Pill label={d.level} color={colors.muted} />
            </View>
            <Text style={s.title} testID="drill-title">{d.title}</Text>
            <Text style={s.desc}>{d.description}</Text>
            <Text style={s.kicker}>HOW TO</Text>
            {d.steps.map((st, i) => (
              <View key={i} style={s.step}>
                <Text style={s.stepNum}>{i + 1}</Text>
                <Text style={s.stepText}>{st}</Text>
              </View>
            ))}
            <Text style={s.kicker}>FIXES</Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: space.sm }}>
              {d.fault_tags.map((t) => <Pill key={t} label={t} color={colors.onSurfaceTertiary} />)}
            </View>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  hero: { height: 280 },
  fill: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  back: { position: "absolute", left: space.lg, width: 44, height: 44, borderRadius: 22, backgroundColor: c.scrim, alignItems: "center", justifyContent: "center" },
  body: { paddingHorizontal: space.lg, gap: space.md, marginTop: -space.xl },
  title: { fontFamily: fonts.display, fontSize: 26, color: c.onSurface, letterSpacing: -0.3 },
  desc: { fontFamily: fonts.text, fontSize: 15, lineHeight: 22, color: c.onSurfaceSecondary },
  kicker: { fontFamily: fonts.textXBold, fontSize: 12, color: c.muted, letterSpacing: 1.5, marginTop: space.md },
  step: { flexDirection: "row", gap: space.md, padding: space.md, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, alignItems: "center" },
  stepNum: { fontFamily: fonts.display, fontSize: 24, color: c.accent, width: 24 },
  stepText: { flex: 1, fontFamily: fonts.text, fontSize: 14, color: c.onSurface },
}));
