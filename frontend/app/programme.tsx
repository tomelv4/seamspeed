import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, ScrollView, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { apiSend, useWeeklyProgramme, WeeklyProgrammeResponse } from "@/src/api";
import { fonts, radius, space } from "@/src/constants";
import { ErrorBanner, Ionicons, Loading, PressScale, PrimaryButton } from "@/src/components/ui";
import { makeStyles, useTheme } from "@/src/theme";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;
type TargetKey = "bowling_days" | "gym_days" | "skill_days" | "match_days";
const TARGETS: { key: TargetKey; label: string; help: string; max: number }[] = [
  { key: "bowling_days", label: "Bowling sessions", help: "High-intensity bowling exposures", max: 4 },
  { key: "gym_days", label: "Strength & conditioning", help: "General gym / physical preparation", max: 4 },
  { key: "skill_days", label: "Technical skill sessions", help: "Low-intensity movement and drill work", max: 4 },
  { key: "match_days", label: "Matches", help: "Count matches as bowling exposures", max: 2 },
];
const TYPE_LABEL: Record<string, string> = { bowling: "BOWLING", gym: "STRENGTH", skill: "SKILL", match: "MATCH", recovery: "RECOVERY", rest: "REST" };

export default function ProgrammeScreen() {
  const s = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const query = useWeeklyProgramme();
  const [targets, setTargets] = useState<Record<TargetKey, number>>({ bowling_days: 2, gym_days: 2, skill_days: 1, match_days: 0 });
  const [unavailable, setUnavailable] = useState<string[]>([]);
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const totalTargets = Object.values(targets).reduce((sum, value) => sum + value, 0);
  const canGenerate = totalTargets + unavailable.length + 1 <= 7 && targets.bowling_days + targets.match_days <= 5 && !saving;

  const generate = async () => {
    if (!canGenerate) return;
    setSaving(true); setError(null);
    try {
      const result = await apiSend<WeeklyProgrammeResponse>("/coach/programme", "POST", { ...targets, unavailable_days: unavailable, notes });
      qc.setQueryData(["coach-programme"], result);
    } catch (e: any) {
      setError(e?.message ?? "Could not generate your weekly programme");
    } finally { setSaving(false); }
  };
  const adjust = (key: TargetKey, delta: number, max: number) =>
    setTargets((current) => ({ ...current, [key]: Math.max(0, Math.min(max, current[key] + delta)) }));
  const toggleUnavailable = (day: string) =>
    setUnavailable((current) => current.includes(day) ? current.filter((item) => item !== day) : [...current, day]);
  const programme = query.data?.programme;

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <PressScale testID="programme-back" style={s.back} onPress={() => router.canGoBack() ? router.back() : router.replace("/coach")}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </PressScale>
        <View style={{ flex: 1 }}>
          <Text style={s.headerTitle}>Training programme</Text>
          <Text style={s.headerSub}>A week built around your cricket</Text>
        </View>
        <View style={s.headerMark}><Ionicons name="calendar" size={20} color={colors.accent} /></View>
      </View>
      <ScrollView contentContainerStyle={{ padding: space.lg, paddingBottom: insets.bottom + space.xl, gap: space.lg }}>
        {query.isLoading ? <Loading /> : null}
        {query.isError ? <ErrorBanner testID="programme-load-error" message="Could not load your saved programme." onRetry={() => query.refetch()} /> : null}
        {programme ? (
          <View style={s.savedPanel} testID="saved-weekly-programme">
            <View style={s.savedHeader}>
              <View style={{ flex: 1, gap: 3 }}>
                <Text style={s.eyebrow}>YOUR SAVED WEEK</Text>
                <Text style={s.savedTitle}>{programme.title}</Text>
                <Text style={s.muted}>Updated {new Date(programme.created_at).toLocaleDateString()}</Text>
              </View>
              <View style={s.savedIcon}><Ionicons name="checkmark" size={19} color={colors.accent} /></View>
            </View>
            <Text style={s.body}>{programme.rationale}</Text>
            <View style={s.workloadNote}>
              <Text style={s.eyebrow}>WORKLOAD WHEN CREATED · {programme.workload_at_generation.status.toUpperCase()}</Text>
              <Text style={s.muted}>{programme.workload_at_generation.headline}</Text>
            </View>
            {programme.days.map((day) => (
              <View key={day.day} style={s.dayCard} testID={"programme-day-" + day.day.toLowerCase()}>
                <View style={s.dayTop}>
                  <Text style={s.dayName}>{day.day}</Text>
                  <Text style={[s.dayType, day.type === "rest" ? s.restType : null]}>{TYPE_LABEL[day.type] ?? day.type.toUpperCase()}</Text>
                </View>
                <Text style={s.dayTitle}>{day.title}</Text>
                {day.focus ? <Text style={s.dayFocus}>{day.focus}</Text> : null}
                <Text style={s.dayDetails}>{day.details}</Text>
                <Text style={s.dayIntensity}>INTENSITY · {day.intensity.toUpperCase()}</Text>
              </View>
            ))}
            <Text style={s.muted}>This is a planning guide, not a medical or injury-risk assessment. Review it with your coach as workload, matches and how you feel change.</Text>
          </View>
        ) : (
          <View style={s.introPanel}>
            <Text style={s.eyebrow}>YOUR DEVELOPMENT PLAN</Text>
            <Text style={s.introTitle}>Build a week that makes sense.</Text>
            <Text style={s.body}>PACED will organise bowling, gym, technical practice, matches and recovery around the days you have available. Your plan is saved so your AI Coach can refer back to it.</Text>
          </View>
        )}
        <View style={s.formPanel} testID="programme-preferences">
          <Text style={s.sectionTitle}>{programme ? "Adjust your weekly plan" : "Set your weekly availability"}</Text>
          <Text style={s.body}>Choose the number of sessions you want to plan. PACED will space hard bowling exposures and include a full rest day.</Text>
          {TARGETS.map((item) => (
            <View key={item.key} style={s.counterRow}>
              <View style={{ flex: 1, gap: 2 }}>
                <Text style={s.counterTitle}>{item.label}</Text>
                <Text style={s.muted}>{item.help}</Text>
              </View>
              <View style={s.counter}>
                <PressScale testID={"programme-" + item.key + "-minus"} style={s.counterButton} disabled={targets[item.key] <= 0} onPress={() => adjust(item.key, -1, item.max)}>
                  <Ionicons name="remove" size={18} color={colors.onSurface} />
                </PressScale>
                <Text style={s.counterValue}>{targets[item.key]}</Text>
                <PressScale testID={"programme-" + item.key + "-plus"} style={s.counterButton} disabled={targets[item.key] >= item.max} onPress={() => adjust(item.key, 1, item.max)}>
                  <Ionicons name="add" size={18} color={colors.onSurface} />
                </PressScale>
              </View>
            </View>
          ))}
          <View style={s.divider} />
          <Text style={s.counterTitle}>Days you are unavailable</Text>
          <Text style={s.muted}>These will be kept free. At least one additional full rest day is protected.</Text>
          <View style={s.dayChips}>
            {DAYS.map((day) => {
              const selected = unavailable.includes(day);
              return (
                <PressScale key={day} testID={"programme-unavailable-" + day.toLowerCase()} style={[s.dayChip, selected ? s.dayChipSelected : null]} onPress={() => toggleUnavailable(day)}>
                  <Text style={[s.dayChipText, selected ? s.dayChipTextSelected : null]}>{day.slice(0, 3)}</Text>
                </PressScale>
              );
            })}
          </View>
          <Text style={s.counterTitle}>Anything else your coach should know?</Text>
          <TextInput testID="programme-notes" style={s.notes} value={notes} onChangeText={setNotes}
            placeholder="e.g. match on Saturday, gym access Tuesday and Thursday, uni or work commitments…"
            placeholderTextColor={colors.muted} multiline maxLength={600} />
          <Text style={s.muted}>{totalTargets + unavailable.length + 1 > 7 ? "Too many sessions for the available days. Reduce a target or remove an unavailable day." : "Your plan will be generated using your latest bowling workload and video-analysis priorities."}</Text>
          {error ? <ErrorBanner testID="programme-error" message={error} /> : null}
          <PrimaryButton testID="programme-generate" label={saving ? "Building your week…" : programme ? "Regenerate and save plan" : "Generate my weekly plan"} disabled={!canGenerate} onPress={generate} />
          {saving ? <ActivityIndicator color={colors.accent} /> : null}
        </View>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: space.md, paddingHorizontal: space.lg, paddingBottom: space.md, borderBottomWidth: 1, borderBottomColor: c.divider },
  back: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center", backgroundColor: c.surfaceTertiary },
  headerTitle: { fontFamily: fonts.display, fontSize: 16, color: c.onSurface, letterSpacing: 0.8 },
  headerSub: { fontFamily: fonts.text, fontSize: 11, color: c.muted },
  headerMark: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center", backgroundColor: c.brandTertiary },
  introPanel: { padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.sm },
  introTitle: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface },
  body: { fontFamily: fonts.text, fontSize: 13, color: c.muted, lineHeight: 19 },
  eyebrow: { fontFamily: fonts.textXBold, fontSize: 10, color: c.accent, letterSpacing: 1.4 },
  savedPanel: { padding: space.md, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.md },
  savedHeader: { flexDirection: "row", alignItems: "center", gap: space.sm },
  savedTitle: { fontFamily: fonts.display, fontSize: 19, color: c.onSurface },
  savedIcon: { width: 34, height: 34, borderRadius: 17, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  muted: { fontFamily: fonts.text, fontSize: 11, color: c.muted, lineHeight: 16 },
  workloadNote: { padding: space.sm, borderRadius: radius.md, backgroundColor: c.surfaceTertiary, gap: 3 },
  dayCard: { padding: space.md, borderRadius: radius.md, backgroundColor: c.surfaceTertiary, gap: 5 },
  dayTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  dayName: { fontFamily: fonts.textBold, fontSize: 12, color: c.onSurface },
  dayType: { fontFamily: fonts.textXBold, fontSize: 9, color: c.accent, letterSpacing: 1 },
  restType: { color: c.muted },
  dayTitle: { fontFamily: fonts.display, fontSize: 15, color: c.onSurface },
  dayFocus: { fontFamily: fonts.textBold, fontSize: 12, color: c.accent },
  dayDetails: { fontFamily: fonts.text, fontSize: 12, color: c.onSurfaceSecondary, lineHeight: 18 },
  dayIntensity: { fontFamily: fonts.textXBold, fontSize: 9, color: c.muted, letterSpacing: 1 },
  formPanel: { padding: space.md, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.md },
  sectionTitle: { fontFamily: fonts.display, fontSize: 18, color: c.onSurface },
  counterRow: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingVertical: space.xs },
  counterTitle: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurface },
  counter: { flexDirection: "row", alignItems: "center", gap: space.sm },
  counterButton: { width: 32, height: 32, borderRadius: 16, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  counterValue: { fontFamily: fonts.display, fontSize: 17, color: c.onSurface, minWidth: 16, textAlign: "center" },
  divider: { height: 1, backgroundColor: c.divider },
  dayChips: { flexDirection: "row", flexWrap: "wrap", gap: space.xs },
  dayChip: { paddingHorizontal: space.md, paddingVertical: space.sm, borderRadius: radius.pill, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceTertiary },
  dayChipSelected: { borderColor: c.accent, backgroundColor: c.brandTertiary },
  dayChipText: { fontFamily: fonts.textBold, fontSize: 11, color: c.onSurface },
  dayChipTextSelected: { color: c.accent },
  notes: { minHeight: 82, borderRadius: radius.md, padding: space.md, backgroundColor: c.surfaceTertiary, color: c.onSurface, fontFamily: fonts.text, fontSize: 13, textAlignVertical: "top" },
}));
