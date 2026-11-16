import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useState } from "react";
import { FlatList, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useDrills } from "@/src/api";
import { IMAGES, PHASES, fonts, phaseLabel, radius, space } from "@/src/constants";
import { EmptyState, ErrorBanner, Ionicons, Loading, Pill, PressScale } from "@/src/components/ui";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme } from "@/src/theme";

const FILTERS = [{ key: "all", label: "All" }, { key: "for_you", label: "For You" }, ...PHASES];

export default function Drills() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const [filter, setFilter] = useState("all");
  const drills = useDrills();
  const data = (drills.data ?? []).filter((d) =>
    filter === "all" ? true : filter === "for_you" ? d.recommended : d.phase === filter,
  );

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <Text style={s.title}>Drills</Text>
        <Text style={s.subtitle}>Personalised to the faults AI finds in your action</Text>
      </View>
      <View style={s.chipRow}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipContent}>
          {FILTERS.map((f) => {
            const active = f.key === filter;
            return (
              <Pressable key={f.key} testID={`drill-filter-${f.key}`} onPress={() => setFilter(f.key)} style={[s.chip, active && s.chipActive]}>
                <Text style={[s.chipText, active && { color: colors.onBrandPrimary }]}>{f.label}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>
      {drills.isLoading ? (
        <Loading testID="drills-loading" />
      ) : drills.isError ? (
        <View style={{ padding: space.lg }}>
          <ErrorBanner testID="drills-error" message="Failed to load drills." onRetry={() => drills.refetch()} />
        </View>
      ) : (
        <FlatList
          data={data}
          keyExtractor={(d) => d.id}
          contentContainerStyle={{ padding: space.lg, paddingBottom: bottomChrome + space.xl, gap: space.md }}
          refreshControl={<RefreshControl tintColor={colors.brandPrimary} refreshing={drills.isRefetching} onRefresh={() => { drills.refetch(); }} />}
          ListEmptyComponent={
            <EmptyState testID="drills-empty" icon="barbell" title="No drills assigned yet" body="Analyze a delivery to get personalised drills for your faults." />
          }
          renderItem={({ item, index }) => (
            <Animated.View entering={FadeInDown.delay(Math.min(index, 6) * 50)}>
              <PressScale testID={`drill-card-${item.id}`} style={s.card} onPress={() => router.push(`/drill/${item.id}`)}>
                <Image source={{ uri: IMAGES.drills[index % IMAGES.drills.length] }} style={s.cardImg} contentFit="cover" transition={200} />
                <LinearGradient colors={[colors.scrimLight, colors.scrim]} style={s.cardImg} />
                <View style={s.cardBody}>
                  <View style={{ flexDirection: "row", gap: space.sm }}>
                    <Pill label={phaseLabel(item.phase)} color={colors.onSurface} />
                    {item.recommended ? <Pill label="For you" color={colors.brandPrimary} icon="flash" testID={`drill-recommended-${item.id}`} /> : null}
                  </View>
                  <Text style={s.cardTitle}>{item.title}</Text>
                  <View style={s.metaRow}>
                    <Ionicons name="time-outline" size={14} color={colors.onSurfaceTertiary} />
                    <Text style={s.meta}>{item.duration}</Text>
                    <Ionicons name="trending-up" size={14} color={colors.onSurfaceTertiary} />
                    <Text style={s.meta}>{item.level}</Text>
                  </View>
                </View>
              </PressScale>
            </Animated.View>
          )}
        />
      )}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: space.lg, paddingBottom: space.sm },
  title: { fontFamily: fonts.display, fontSize: 32, color: c.onSurface, textTransform: "uppercase" },
  subtitle: { fontFamily: fonts.text, fontSize: 13, color: c.muted },
  chipRow: { height: 56, justifyContent: "center", borderBottomWidth: 1, borderBottomColor: c.divider },
  chipContent: { gap: space.sm, paddingHorizontal: space.lg, alignItems: "center" },
  chip: { height: 36, flexShrink: 0, paddingHorizontal: space.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, justifyContent: "center" },
  chipActive: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  chipText: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurfaceTertiary },
  card: { height: 190, borderRadius: radius.lg, overflow: "hidden", backgroundColor: c.surfaceSecondary },
  cardImg: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0 },
  cardBody: { flex: 1, justifyContent: "flex-end", padding: space.lg, gap: space.sm },
  cardTitle: { fontFamily: fonts.display, fontSize: 26, color: c.onSurface, textTransform: "uppercase" },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  meta: { fontFamily: fonts.text, fontSize: 12, color: c.onSurfaceTertiary, marginRight: space.sm },
}));
