import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { apiGet, apiSend, CoachMessage, streamCoach, useDrillPracticeHistory, useWorkload } from "@/src/api";
import { fonts, radius, space } from "@/src/constants";
import { ErrorBanner, Ionicons, PressScale, PrimaryButton } from "@/src/components/ui";
import { ProLocked } from "@/src/components/ProLocked";
import { useSubscription } from "@/src/revenuecat";
import { makeStyles, useTheme } from "@/src/theme";

const PROMPTS = [
  "How can I bowl quicker?",
  "Explain my biggest fault",
  "Is my action safe for my back?",
  "Give me a 4-week pace plan",
];

type Msg = Pick<CoachMessage, "role" | "content"> & { id: string };

export default function Coach() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const history = useQuery({ queryKey: ["coach"], queryFn: () => apiGet<CoachMessage[]>("/coach/messages") });
  const practice = useDrillPracticeHistory();
  const workload = useWorkload();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<FlatList<Msg>>(null);
  const { isSubscribed, isLoading: subLoading } = useSubscription();

  useEffect(() => {
    if (history.data) setMsgs(history.data.map((m) => ({ id: m.id, role: m.role, content: m.content })));
  }, [history.data]);

  const send = async (raw: string) => {
    const message = raw.trim();
    if (!message || sending) return;
    setText("");
    setError(null);
    setSending(true);
    const aid = `a-${Date.now()}`;
    setMsgs((m) => [...m, { id: `u-${Date.now()}`, role: "user", content: message }, { id: aid, role: "assistant", content: "" }]);
    try {
      await streamCoach(message, (delta) =>
        setMsgs((m) => m.map((x) => (x.id === aid ? { ...x, content: x.content + delta } : x))),
      );
    } catch (e: any) {
      setError(e?.message ?? "Coach unavailable");
      setMsgs((m) => m.filter((x) => !(x.id === aid && !x.content)));
    } finally {
      setSending(false);
    }
  };

  const clear = async () => {
    try {
      await apiSend("/coach/messages", "DELETE");
      setMsgs([]);
      setError(null);
      qc.invalidateQueries({ queryKey: ["coach"] });
    } catch (e: any) {
      setError(e?.message ?? "Could not clear chat");
    }
  };

  if (!subLoading && !isSubscribed) {
    return (
      <View style={[s.screen, { padding: space.lg, paddingTop: insets.top + space.lg, justifyContent: "center", gap: space.md }]}>
        <ProLocked testID="coach-locked" title="AI Coach is Pro" body="Chat with your ChatGPT-powered fast-bowling coach about pace, swing and injury prevention." />
        <PrimaryButton testID="coach-locked-back" label="Go back" variant="secondary" onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} />
      </View>
    );
  }

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <View style={s.iconBtn}>
          <Ionicons name="fitness" size={21} color={colors.accent} />
        </View>
        <View style={{ flex: 1, alignItems: "center" }}>
          <Text style={s.headerTitle}>AI Coach</Text>
          <Text style={s.headerSub}>Powered by ChatGPT</Text>
        </View>
        <PressScale testID="coach-clear-button" style={s.iconBtn} onPress={clear}>
          <Ionicons name="refresh" size={20} color={colors.onSurface} />
        </PressScale>
      </View>

      <KeyboardAvoidingView behavior="padding" style={{ flex: 1 }}>
        <FlatList
          ref={listRef}
          data={msgs}
          keyExtractor={(m) => m.id}
          contentContainerStyle={{ padding: space.lg, paddingBottom: space.xl, gap: space.md, flexGrow: 1 }}
          style={{ flex: 1 }}
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
          onLayout={() => listRef.current?.scrollToEnd({ animated: false })}
          keyboardShouldPersistTaps="handled"
          ListHeaderComponent={
            <View style={{ gap: space.md, paddingBottom: space.md }}>
              <View style={s.hubPanel} testID="coach-training-hub">
                <View style={{ gap: 3 }}>
                  <Text style={s.hubEyebrow}>YOUR DEVELOPMENT CENTRE</Text>
                  <Text style={s.hubTitle}>Train with a plan.</Text>
                  <Text style={s.hubBody}>Your coach connects technique, training, workload and recovery in one place.</Text>
                </View>
                <View style={s.hubWorkload}>
                  <View style={{ flex: 1, gap: 2 }}>
                    <Text style={s.practiceTitle}>CURRENT WORKLOAD</Text>
                    <Text style={s.hubWorkloadValue}>{workload.data ? workload.data.status.toUpperCase() : workload.isLoading ? "LOADING" : "NOT AVAILABLE"}</Text>
                    <Text style={s.practiceHint} numberOfLines={2}>{workload.data?.headline ?? "Log your bowling to help your coach plan appropriate training and recovery."}</Text>
                  </View>
                  <View style={{ alignItems: "flex-end", gap: 2 }}>
                    <Text style={s.hubBalls}>{workload.data?.acute ?? "—"}</Text>
                    <Text style={s.practiceHint}>balls · 7 days</Text>
                  </View>
                </View>
                <PressScale testID="coach-start-session" style={s.hubAction} onPress={() => router.push("/session")}>
                  <View style={s.hubActionIcon}><Ionicons name="play" size={17} color={colors.accent} /></View>
                  <View style={{ flex: 1, gap: 2 }}>
                    <Text style={s.hubActionTitle}>Start a guided session</Text>
                    <Text style={s.hubActionBody}>Readiness, warm-up, drills, bowling and recovery</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={17} color={colors.muted} />
                </PressScale>
                <PressScale testID="coach-open-workload" style={s.hubAction} onPress={() => router.push("/workload")}>
                  <View style={s.hubActionIcon}><Ionicons name="pulse" size={17} color={colors.accent} /></View>
                  <View style={{ flex: 1, gap: 2 }}>
                    <Text style={s.hubActionTitle}>Workload and recovery</Text>
                    <Text style={s.hubActionBody}>Bowling volume, intensity and rest days</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={17} color={colors.muted} />
                </PressScale>
                <PressScale testID="coach-open-drills" style={s.hubAction} onPress={() => router.push("/drills")}>
                  <View style={s.hubActionIcon}><Ionicons name="barbell" size={17} color={colors.accent} /></View>
                  <View style={{ flex: 1, gap: 2 }}>
                    <Text style={s.hubActionTitle}>Technique drill library</Text>
                    <Text style={s.hubActionBody}>Build practice around your video-analysis priorities</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={17} color={colors.muted} />
                </PressScale>
                <PressScale testID="coach-build-week" style={[s.hubAction, s.hubActionPrimary]} onPress={() => send("Build me a practical weekly fast-bowling development plan. Integrate my recent bowling workload, technique priorities, strength and conditioning, skill practice, warm-ups, cool-downs, recovery and rest days. Ask me for any essential schedule constraints you do not know. Explain how the sessions fit together and how to adjust if I am fatigued or sore.")}>
                  <View style={[s.hubActionIcon, s.hubActionIconPrimary]}><Ionicons name="calendar" size={17} color={colors.onBrandPrimary} /></View>
                  <View style={{ flex: 1, gap: 2 }}>
                    <Text style={[s.hubActionTitle, { color: colors.onBrandPrimary }]}>Plan my training week</Text>
                    <Text style={[s.hubActionBody, { color: colors.onBrandPrimary, opacity: 0.78 }]}>Personalised bowling, gym, skill and recovery schedule</Text>
                  </View>
                  <Ionicons name="arrow-forward" size={17} color={colors.onBrandPrimary} />
                </PressScale>
              </View>
              {!practice.isLoading ? (
                <View style={s.practicePanel} testID="coach-practice-history">
                  <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                    <Text style={s.practiceTitle}>YOUR PRACTICE LOG</Text>
                    <Text style={s.practiceCount}>{practice.data?.total_completions ?? 0} sessions logged</Text>
                  </View>
                  {(practice.data?.focuses ?? []).slice(0, 3).map((item) => (
                    <View key={item.step_key} style={s.practiceRow}>
                      <View style={{ flex: 1, gap: 2 }}>
                        <Text style={s.practiceFocus}>{item.focus}</Text>
                        <Text style={s.practiceDrill}>{item.drill_name} · last {new Date(item.last_completed_at).toLocaleDateString()}</Text>
                      </View>
                      <Text style={s.practiceCount}>×{item.completed_count}</Text>
                    </View>
                  ))}
                  <Text style={s.practiceHint}>{practice.data?.total_completions ? "Your coach uses this history to follow up on practice and compare future video evidence." : "When a report recommends a targeted drill, log each session there. Your coach will remember the work and check for changes in future comparable videos."}</Text>
                </View>
              ) : null}
            </View>
          }
          ListEmptyComponent={
            history.isLoading ? (
              <ActivityIndicator color={colors.accent} />
            ) : (
              <View style={s.empty} testID="coach-empty">
                <View style={s.emptyIcon}>
                  <Ionicons name="chatbubbles" size={30} color={colors.accent} />
                </View>
                <Text style={s.emptyTitle}>Your fast-bowling coach</Text>
                <Text style={s.emptyBody}>Ask anything about pace, swing, your action or injury prevention. I know your latest reports.</Text>
              </View>
            )
          }
          renderItem={({ item }) => (
            <View style={[s.bubble, item.role === "user" ? s.user : s.bot]} testID={`coach-message-${item.role}`}>
              {item.content ? (
                <Text style={[s.bubbleText, item.role === "user" && { color: colors.onBrandPrimary }]}>{item.content.replace(/\*\*/g, "").replace(/^#+\s/gm, "")}</Text>
              ) : (
                <ActivityIndicator size="small" color={colors.accent} />
              )}
            </View>
          )}
        />
        {error ? <View style={{ paddingHorizontal: space.lg }}><ErrorBanner testID="coach-error" message={error} /></View> : null}
        {msgs.length === 0 && !history.isLoading ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }} contentContainerStyle={s.prompts}>
            {PROMPTS.map((p, i) => (
              <Pressable key={p} testID={`coach-prompt-${i}`} style={s.prompt} onPress={() => send(p)}>
                <Text style={s.promptText}>{p}</Text>
              </Pressable>
            ))}
          </ScrollView>
        ) : null}
        <View style={[s.inputBar, { paddingBottom: insets.bottom + space.sm }]}>
          <TextInput
            testID="coach-input"
            style={s.input}
            value={text}
            onChangeText={setText}
            placeholder="Ask your coach…"
            placeholderTextColor={colors.muted}
            multiline
            maxLength={1000}
          />
          <PressScale testID="coach-send-button" style={[s.send, (!text.trim() || sending) && { opacity: 0.5 }]} disabled={!text.trim() || sending} onPress={() => send(text)}>
            {sending ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Ionicons name="arrow-up" size={22} color={colors.onBrandPrimary} />}
          </PressScale>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: space.lg, paddingBottom: space.sm, borderBottomWidth: 1, borderBottomColor: c.divider },
  headerTitle: { fontFamily: fonts.display, fontSize: 15, color: c.onSurface, textTransform: "uppercase", letterSpacing: 2.5 },
  headerSub: { fontFamily: fonts.text, fontSize: 11, color: c.muted },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", gap: space.sm, padding: space.xl },
  emptyIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  emptyTitle: { fontFamily: fonts.display, fontSize: 18, color: c.onSurface, letterSpacing: 0.5 },
  emptyBody: { fontFamily: fonts.text, fontSize: 14, color: c.muted, textAlign: "center", lineHeight: 20 },
  hubPanel: { padding: space.md, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.sm },
  hubEyebrow: { fontFamily: fonts.textXBold, fontSize: 10, color: c.accent, letterSpacing: 1.5 },
  hubTitle: { fontFamily: fonts.display, fontSize: 21, color: c.onSurface, letterSpacing: 0.3 },
  hubBody: { fontFamily: fonts.text, fontSize: 12, color: c.muted, lineHeight: 17 },
  hubWorkload: { flexDirection: "row", alignItems: "center", padding: space.sm, borderRadius: radius.md, backgroundColor: c.surfaceTertiary, gap: space.sm },
  hubWorkloadValue: { fontFamily: fonts.display, fontSize: 18, color: c.onSurface },
  hubBalls: { fontFamily: fonts.display, fontSize: 24, color: c.accent },
  hubAction: { flexDirection: "row", alignItems: "center", gap: space.sm, padding: space.sm, borderRadius: radius.md, backgroundColor: c.surfaceTertiary },
  hubActionPrimary: { backgroundColor: c.brandPrimary, marginTop: space.xs },
  hubActionIcon: { width: 34, height: 34, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", backgroundColor: c.brandTertiary },
  hubActionIconPrimary: { backgroundColor: "rgba(255,255,255,0.14)" },
  hubActionTitle: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurface },
  hubActionBody: { fontFamily: fonts.text, fontSize: 11, color: c.muted, lineHeight: 15 },
  practicePanel: { padding: space.md, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.sm },
  practiceTitle: { fontFamily: fonts.textXBold, fontSize: 10, color: c.muted, letterSpacing: 1.4 },
  practiceCount: { fontFamily: fonts.textBold, fontSize: 11, color: c.accent },
  practiceRow: { flexDirection: "row", alignItems: "center", gap: space.sm, paddingTop: space.xs, borderTopWidth: 1, borderTopColor: c.divider },
  practiceFocus: { fontFamily: fonts.textBold, fontSize: 12, color: c.onSurface },
  practiceDrill: { fontFamily: fonts.text, fontSize: 11, color: c.muted },
  practiceHint: { fontFamily: fonts.text, fontSize: 11, color: c.onSurfaceTertiary, lineHeight: 15 },
  bubble: { maxWidth: "85%", padding: space.md, borderRadius: radius.lg },
  user: { alignSelf: "flex-end", backgroundColor: c.brandPrimary, borderBottomRightRadius: radius.sm },
  bot: { alignSelf: "flex-start", backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, borderBottomLeftRadius: radius.sm },
  bubbleText: { fontFamily: fonts.text, fontSize: 14, lineHeight: 21, color: c.onSurfaceSecondary },
  prompts: { gap: space.sm, paddingHorizontal: space.lg, paddingBottom: space.sm, alignItems: "center" },
  prompt: { height: 44, flexShrink: 0, paddingHorizontal: space.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: c.borderStrong, justifyContent: "center", backgroundColor: c.surfaceSecondary },
  promptText: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurface },
  inputBar: { flexDirection: "row", alignItems: "flex-end", gap: space.sm, paddingHorizontal: space.lg, paddingTop: space.sm, borderTopWidth: 1, borderTopColor: c.divider, backgroundColor: c.surface },
  input: { flex: 1, minHeight: 48, maxHeight: 120, borderRadius: 24, paddingHorizontal: space.lg, paddingTop: 13, paddingBottom: 13, backgroundColor: c.surfaceTertiary, color: c.onSurface, fontFamily: fonts.text, fontSize: 15 },
  send: { width: 48, height: 48, borderRadius: 24, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
}));
