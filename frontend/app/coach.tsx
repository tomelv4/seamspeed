import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { apiGet, apiSend, CoachMessage, streamCoach } from "@/src/api";
import { fonts, radius, space } from "@/src/constants";
import { ErrorBanner, Ionicons, PressScale } from "@/src/components/ui";
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
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<FlatList<Msg>>(null);

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

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <PressScale testID="coach-back-button" style={s.iconBtn} onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </PressScale>
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
          ListEmptyComponent={
            history.isLoading ? (
              <ActivityIndicator color={colors.brandPrimary} />
            ) : (
              <View style={s.empty} testID="coach-empty">
                <View style={s.emptyIcon}>
                  <Ionicons name="chatbubbles" size={30} color={colors.brandPrimary} />
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
                <ActivityIndicator size="small" color={colors.brandPrimary} />
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
  headerTitle: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface, textTransform: "uppercase" },
  headerSub: { fontFamily: fonts.text, fontSize: 11, color: c.muted },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  empty: { flex: 1, alignItems: "center", justifyContent: "center", gap: space.sm, padding: space.xl },
  emptyIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  emptyTitle: { fontFamily: fonts.display, fontSize: 26, color: c.onSurface, textTransform: "uppercase" },
  emptyBody: { fontFamily: fonts.text, fontSize: 14, color: c.muted, textAlign: "center", lineHeight: 20 },
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
