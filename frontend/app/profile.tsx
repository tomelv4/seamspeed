import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import * as Clipboard from "expo-clipboard";
import { Pressable, Switch, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { apiSend, getDeviceId, Profile, useProfile } from "@/src/api";
import { useSubscription } from "@/src/revenuecat";
import { fonts, radius, space } from "@/src/constants";
import { ErrorBanner, Ionicons, PressScale, PrimaryButton } from "@/src/components/ui";
import { makeStyles, useTheme } from "@/src/theme";

const OPTIONS: { key: keyof Profile; label: string; values: string[] }[] = [
  { key: "bowling_arm", label: "Bowling arm", values: ["Right", "Left"] },
  { key: "bowling_style", label: "Style", values: ["Express", "Fast", "Fast-medium", "Medium"] },
  { key: "level", label: "Level", values: ["Junior", "Club", "Academy", "Pro"] },
  { key: "age_band", label: "Age (affects back-injury and workload guidance)", values: ["Under 16", "16-18", "19-22", "23+"] },
];

export default function ProfileScreen() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const profile = useProfile();
  const [form, setForm] = useState<Profile>({ name: "", bowling_arm: "Right", bowling_style: "Fast", level: "Club" });
  const [saving, setSaving] = useState(false);
  const { devPro, setDevPro } = useSubscription();
  const [deviceId, setDeviceId] = useState("");
  useEffect(() => {
    getDeviceId().then(setDeviceId);
  }, []);
  const [error, setError] = useState<string | null>(null);

  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!profile.data || loaded) return;
    setLoaded(true);
    setForm({ name: profile.data.name, bowling_arm: profile.data.bowling_arm, bowling_style: profile.data.bowling_style, level: profile.data.level, age_band: profile.data.age_band ?? "" });
  }, [profile.data, loaded]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      await apiSend("/profile", "PUT", { ...form, name: form.name.trim() || "Bowler" });
      await qc.invalidateQueries({ queryKey: ["profile"] });
      router.canGoBack() ? router.back() : router.replace("/");
    } catch (e: any) {
      setError(e?.message ?? "Could not save profile");
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <Text style={s.title}>Bowler Profile</Text>
        <PressScale testID="profile-close-button" style={s.iconBtn} onPress={() => router.back()}>
          <Ionicons name="close" size={22} color={colors.onSurface} />
        </PressScale>
      </View>
      <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ padding: space.lg, paddingBottom: insets.bottom + space.xl, gap: space.xl }}>
        <Text style={s.help}>Your profile helps the AI tailor analysis and coaching to your action.</Text>
        <View style={{ gap: space.sm }}>
          <Text style={s.label}>Name</Text>
          <TextInput
            testID="profile-name-input"
            style={s.input}
            value={form.name}
            onChangeText={(name) => setForm((f) => ({ ...f, name }))}
            placeholder="Your name"
            placeholderTextColor={colors.muted}
            maxLength={40}
          />
        </View>
        {OPTIONS.map((o) => (
          <View key={o.key} style={{ gap: space.sm }}>
            <Text style={s.label}>{o.label}</Text>
            <View style={s.options}>
              {o.values.map((v) => {
                const active = form[o.key] === v;
                return (
                  <Pressable key={v} testID={`profile-${o.key}-${v.toLowerCase().replace(" ", "-")}`} onPress={() => setForm((f) => ({ ...f, [o.key]: v }))} style={[s.chip, active && s.chipActive]}>
                    <Text style={[s.chipText, active && { color: colors.onBrandPrimary }]}>{v}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
        ))}
        {error ? <ErrorBanner testID="profile-error" message={error} /> : null}
        <PrimaryButton testID="profile-save-button" label="Save Profile" icon="checkmark" onPress={save} loading={saving} />
        {__DEV__ ? (
          <View testID="dev-tools" style={s.devCard}>
            <Text style={s.label}>DEVELOPER (test builds only)</Text>
            <View style={s.devRow}>
              <View style={{ flex: 1 }}>
                <Text style={s.devTitle}>Unlock Pro for testing</Text>
                <Text style={s.help}>Free Pro on this device. Not available in the store app.</Text>
              </View>
              <Switch testID="dev-pro-switch" value={devPro} onValueChange={setDevPro} trackColor={{ true: colors.brandPrimary, false: colors.border }} thumbColor={colors.onSurface} />
            </View>
          </View>
        ) : null}
        {deviceId ? (
          <Pressable testID="profile-device-id" onLongPress={() => Clipboard.setStringAsync(deviceId)}>
            <Text style={s.help}>Device ID (hold to copy): {deviceId}</Text>
          </Pressable>
        ) : null}
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: space.lg, paddingBottom: space.sm, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontFamily: fonts.display, fontSize: 18, color: c.onSurface, textTransform: "uppercase", letterSpacing: 2.5 },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  help: { fontFamily: fonts.text, fontSize: 14, color: c.muted, lineHeight: 20 },
  label: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurfaceTertiary },
  input: { height: 52, borderRadius: radius.md, backgroundColor: c.surfaceTertiary, color: c.onSurface, paddingHorizontal: space.lg, fontFamily: fonts.text, fontSize: 15, borderWidth: 1, borderColor: c.border },
  options: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  chip: { height: 40, paddingHorizontal: space.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, justifyContent: "center" },
  chipActive: { backgroundColor: c.brandPrimary, borderColor: c.accentLine },
  devCard: { marginTop: space.lg, padding: space.lg, gap: space.sm, borderRadius: radius.md, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary },
  devRow: { flexDirection: "row", alignItems: "center", gap: space.md },
  devTitle: { fontFamily: fonts.textBold, fontSize: 15, color: c.onSurface },
  chipText: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurfaceTertiary },
}));
