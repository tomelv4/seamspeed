import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { RefreshControl, ScrollView, Text, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAnalyses, useProfile } from "@/src/api";
import { IMAGES, fonts, phaseLabel, radius, space } from "@/src/constants";
import { SessionRow } from "@/src/components/SessionRow";
import { EmptyState, ErrorBanner, Ionicons, Loading, Pill, PressScale, PrimaryButton, SectionTitle, Wordmark, riskColor } from "@/src/components/ui";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme } from "@/src/theme";

export default function Home() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const analyses = useAnalyses();
  const profile = useProfile();
  const list = analyses.data ?? [];
  const latest = list.find((a) => a.is_bowling_video);

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <View>
          <Text style={s.hello}>Performance Lab · {profile.data?.name ?? "Bowler"}</Text>
          <Wordmark />
        </View>
        <PressScale testID="open-profile-button" style={s.iconBtn} onPress={() => router.push("/profile")}>
          <Ionicons name="person" size={20} color={colors.onSurface} />
        </PressScale>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: space.lg, paddingBottom: bottomChrome + space.xl, gap: space.xl }}
        refreshControl={<RefreshControl tintColor={colors.accent} refreshing={analyses.isRefetching} onRefresh={() => { analyses.refetch(); profile.refetch(); }} />}
      >
        <Animated.View entering={FadeInDown.duration(400)} style={s.hero} testID="home-hero-card">
          <Image source={{ uri: IMAGES.hero }} style={s.heroImg} contentFit="cover" transition={300} />
          <LinearGradient colors={[colors.scrimLight, colors.scrim]} style={s.heroScrim} />
          <View style={s.heroContent}>
            {latest ? (
              <>
                <Text style={s.heroLabel}>LATEST DELIVERY</Text>
                <View style={s.heroScoreRow}>
                  <Text style={s.heroScore} testID="home-latest-score">{latest.overall_score_assessable === false ? "—" : latest.overall_score.toFixed(1)}</Text>
                  <Text style={s.heroOutOf}>/10</Text>
                </View>
                <View style={{ flexDirection: "row", gap: space.sm, flexWrap: "wrap" }}>
                  <Pill label={latest.pace_band?.label || "Pace n/a"} color={colors.onSurface} icon="speedometer" />
                  <Pill label={latest.injury_risk?.level === "not_assessed" ? "Injury risk not assessed" : `${latest.injury_risk?.level || "Not assessed"} risk`} color={latest.injury_risk?.level === "not_assessed" ? colors.muted : riskColor(latest.injury_risk?.level, colors)} icon="shield-checkmark" />
                </View>
              </>
            ) : (
              <>
                <Text style={s.heroLabel}>BIOMECHANICS ANALYSIS</Text>
                <Text style={s.heroTitle}>Precision analysis{"\n"}for fast bowlers.</Text>
              </>
            )}
            <PrimaryButton testID="home-analyze-cta" label="New Analysis" icon="videocam" onPress={() => router.push("/analyze")} />
          </View>
        </Animated.View>

        <Animated.View entering={FadeInDown.delay(100).duration(400)}>
          <PressScale testID="home-coach-card" style={s.coach} onPress={() => router.push("/coach")}>
            <View style={[s.coachIcon, { backgroundColor: colors.brandPrimary }]}>
              <Ionicons name="chatbubbles" size={22} color={colors.onBrandPrimary} />
            </View>
            <View style={{ flex: 1, gap: 3 }}>
              <Text style={s.coachTitle}>AI Coach</Text>
              <Text style={s.coachBody}>Your complete training hub for technique, guided sessions, workload, strength and conditioning, and recovery.</Text>
            </View>
            <Ionicons name="arrow-forward" size={20} color={colors.muted} />
          </PressScale>
        </Animated.View>

        {latest && latest.faults.length > 0 ? (
          <Animated.View entering={FadeInDown.delay(200).duration(400)}>
            <SectionTitle title="Focus Areas" action="Coach" onAction={() => router.push("/coach")} testID="focus-see-drills" />
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: space.md }}>
              {latest.faults.map((f, i) => (
                <PressScale key={i} testID={`focus-fault-${i}`} style={s.fault} onPress={() => router.push(`/report/${latest.id}`)}>
                  <Pill label={f.severity} color={riskColor(f.severity, colors)} />
                  <Text style={s.faultTitle} numberOfLines={2}>{f.title}</Text>
                  <Text style={s.faultPhase}>{phaseLabel(f.phase)}</Text>
                </PressScale>
              ))}
            </ScrollView>
          </Animated.View>
        ) : null}

        <Animated.View entering={FadeInDown.delay(300).duration(400)}>
          <SectionTitle title="Recent Sessions" action={list.length ? "All" : undefined} onAction={() => router.push("/progress")} testID="recent-see-all" />
          {analyses.isLoading ? (
            <Loading testID="home-loading" />
          ) : analyses.isError ? (
            <ErrorBanner testID="home-error" message="Failed to load sessions." onRetry={() => analyses.refetch()} />
          ) : list.length === 0 ? (
            <EmptyState testID="home-empty" icon="baseball" title="No sessions yet" body="Upload your first delivery to get a full biomechanics report." />
          ) : (
            list.slice(0, 5).map((a) => <SessionRow key={a.id} item={a} />)
          )}
        </Animated.View>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", paddingHorizontal: space.lg, paddingBottom: space.sm, backgroundColor: c.surface, borderBottomWidth: 1, borderBottomColor: c.divider },
  hello: { fontFamily: fonts.text, fontSize: 13, color: c.muted },
  wordmark: { fontFamily: fonts.display, fontSize: 30, color: c.onSurface, letterSpacing: 1 },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  hero: { borderRadius: radius.lg, overflow: "hidden", minHeight: 340, backgroundColor: c.surfaceSecondary },
  heroImg: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  heroScrim: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  heroContent: { flex: 1, justifyContent: "flex-end", padding: space.lg, gap: space.md },
  heroLabel: { fontFamily: fonts.textXBold, fontSize: 12, color: c.accent, letterSpacing: 1.5 },
  heroScoreRow: { flexDirection: "row", alignItems: "flex-end" },
  heroScore: { fontFamily: fonts.displaySemi, fontSize: 72, lineHeight: 80, letterSpacing: -2, color: c.onSurface },
  heroOutOf: { fontFamily: fonts.displaySemi, fontSize: 28, color: c.muted, marginBottom: 10, marginLeft: 4 },
  heroTitle: { fontFamily: fonts.display, fontSize: 28, lineHeight: 34, color: c.onSurface, letterSpacing: -0.3 },
  coach: { flexDirection: "row", alignItems: "center", gap: space.md, padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  coachIcon: { width: 48, height: 48, borderRadius: 24, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  coachTitle: { fontFamily: fonts.textXBold, fontSize: 16, color: c.onSurface },
  coachBody: { fontFamily: fonts.text, fontSize: 12, color: c.muted, marginTop: 2 },
  fault: { width: 170, padding: space.md, gap: space.sm, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  faultTitle: { fontFamily: fonts.textBold, fontSize: 14, color: c.onSurface, minHeight: 38 },
  faultPhase: { fontFamily: fonts.text, fontSize: 12, color: c.muted },
}));
