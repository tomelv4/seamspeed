import { useQueryClient } from "@tanstack/react-query";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as ImagePicker from "expo-image-picker";
import { useFocusEffect, useRouter } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, AppState, Linking, Platform, Pressable, ScrollView, Text, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { apiSend, Ball, CoachSession, ttsUrl, uploadBall } from "@/src/api";
import { playCoach, stopCoach } from "@/src/coachAudio";
import { fonts, radius, space } from "@/src/constants";
import { ProLocked } from "@/src/components/ProLocked";
import { PlanStage } from "@/src/components/PlanStage";

type Stage = "warm_up" | "drills" | "bowling" | "test" | "cool_down";
const STAGES: { key: Stage; label: string }[] = [
  { key: "warm_up", label: "Warm-up" }, { key: "drills", label: "Drills" }, { key: "bowling", label: "Bowling" },
  { key: "test", label: "Test" }, { key: "cool_down", label: "Cool-down" },
];
import { ErrorBanner, Ionicons, PressScale, PrimaryButton, scoreColor } from "@/src/components/ui";
import { useSubscription } from "@/src/revenuecat";
import { makeStyles, useTheme } from "@/src/theme";

const FOCUSES = ["Pace", "Accuracy", "Efficient Action", "Swing", "Yorkers"];

export default function LiveSession() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const { isSubscribed, isLoading: subLoading } = useSubscription();
  const [permission, requestPermission] = useCameraPermissions();
  const camRef = useRef<CameraView>(null);
  const [focus, setFocus] = useState("Pace");
  const [session, setSession] = useState<CoachSession | null>(null);
  const [balls, setBalls] = useState<Ball[]>([]);
  const [message, setMessage] = useState<{ text: string; target?: string; audio?: string } | null>(null);
  const [busy, setBusy] = useState<null | "starting" | "watching" | "ending">(null);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stage, setStage] = useState<Stage>("warm_up");
  const canRecord = Platform.OS !== "web";

  useFocusEffect(useCallback(() => () => stopCoach(), []));
  useEffect(() => {
    const sub = AppState.addEventListener("change", (st) => st !== "active" && stopCoach());
    return () => sub.remove();
  }, []);

  const say = async (audio?: string) => {
    if (!audio) return;
    try {
      await playCoach(ttsUrl(audio));
    } catch {
      setError("Couldn't play the coach's voice. Tap replay to try again.");
    }
  };

  const start = async () => {
    setBusy("starting");
    setError(null);
    try {
      const sess = await apiSend<CoachSession>("/sessions", "POST", { focus });
      setSession(sess);
      setBalls([]);
      setMessage({ text: sess.intro, audio: sess.intro_audio });
      setStage("warm_up");
      say(sess.intro_audio);
    } catch (e: any) {
      setError(e?.message ?? "Could not start the session");
    } finally {
      setBusy(null);
    }
  };

  const submit = async (file: { uri: string; name?: string; mimeType?: string }) => {
    if (!session) return;
    stopCoach();
    setBusy("watching");
    setError(null);
    try {
      const ball = await uploadBall(session.id, file, stage === "test" ? "test" : "bowling");
      setBalls((b) => [...b, ball]);
      qc.invalidateQueries({ queryKey: ["workload"] });
      setMessage({ text: ball.feedback, target: ball.next_target, audio: ball.audio });
      say(ball.audio);
    } catch (e: any) {
      setError(e?.message ?? "Coach could not review that ball. Try again.");
    } finally {
      setBusy(null);
    }
  };

  const toggleRecord = async () => {
    if (recording) {
      camRef.current?.stopRecording();
      return;
    }
    stopCoach();
    setRecording(true);
    try {
      const res = await camRef.current?.recordAsync({ maxDuration: 15 });
      setRecording(false);
      if (res?.uri) {
        const ios = Platform.OS === "ios";
        submit({ uri: res.uri, name: ios ? "ball.mov" : "ball.mp4", mimeType: ios ? "video/quicktime" : "video/mp4" });
      }
    } catch (e: any) {
      setRecording(false);
      setError(e?.message ?? "Recording failed");
    }
  };

  const uploadClip = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["videos"], quality: 0.7 });
    if (!res.canceled && res.assets?.[0]) {
      const a = res.assets[0];
      submit({ uri: a.uri, name: a.fileName ?? "ball.mp4", mimeType: a.mimeType ?? "video/mp4" });
    }
  };

  const end = async () => {
    if (!session) return;
    stopCoach();
    setBusy("ending");
    try {
      const done = await apiSend<CoachSession>(`/sessions/${session.id}/end`, "POST");
      setSession(done);
      setMessage({ text: done.summary, audio: done.summary_audio });
      say(done.summary_audio);
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["workload"] });
    } catch (e: any) {
      setError(e?.message ?? "Could not end session");
    } finally {
      setBusy(null);
    }
  };

  const back = () => {
    stopCoach();
    router.canGoBack() ? router.back() : router.replace("/");
  };

  const avg = balls.length ? balls.reduce((a, b) => a + b.score, 0) / balls.length : 0;
  const targetHits = balls.filter((b) => b.hit_target).length;
  const ended = session?.status === "ended";
  const plan = session?.plan ?? {};
  const stageIdx = STAGES.findIndex((x) => x.key === stage);
  const isBowl = stage === "bowling" || stage === "test";
  const blockBalls = balls.filter((b) => (b.block ?? "bowling") === (stage === "test" ? "test" : "bowling"));

  const advance = async (next: Stage) => {
    stopCoach();
    setStage(next);
    const text =
      next === "drills" ? `Warm-up done. Now technique drills: ${(plan.drills ?? []).map((d) => d.name).join(", ")}.`
      : next === "bowling" ? `Drills done. Bowling block: ${plan.bowling?.balls ?? 6} balls. First target: ${plan.bowling?.target ?? "hit a good length"}. Bowl when ready.`
      : next === "test" ? `Time for the test: ${plan.test?.name ?? "skills test"}. ${plan.test?.balls ?? 6} balls. Success means ${plan.test?.target ?? "hitting the target"}. Bowl when ready.`
      : "Great bowling. Let's cool down properly to protect your body.";
    setMessage({ text });
    try {
      const { audio } = await apiSend<{ audio: string }>("/speak", "POST", { text });
      setMessage({ text, audio });
      say(audio);
    } catch {}
  };

  if (!subLoading && !isSubscribed) {
    return (
      <View style={[s.screen, { padding: space.lg, paddingTop: insets.top + space.lg, justifyContent: "center" }]}>
        <ProLocked testID="session-locked" title="Live AI Coaching" body="Film ball after ball while your AI coach talks you through the session. Pro feature." />
        <PrimaryButton testID="session-locked-back" label="Go back" variant="secondary" onPress={back} />
      </View>
    );
  }

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <PressScale testID="session-back-button" style={s.iconBtn} onPress={back}>
          <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
        </PressScale>
        <View style={{ flex: 1, alignItems: "center" }}>
          <Text style={s.headerTitle}>Live Session</Text>
          <Text style={s.headerSub}>{session ? `${session.focus} · ${balls.length} ${balls.length === 1 ? "ball" : "balls"}` : "AI net coach"}</Text>
        </View>
        {session && !ended ? (
          <Pressable testID="session-end-button" style={s.endBtn} onPress={end} disabled={!!busy}>
            <Text style={s.endText}>End</Text>
          </Pressable>
        ) : <View style={{ width: 44 }} />}
      </View>

      <ScrollView contentContainerStyle={{ padding: space.lg, paddingBottom: insets.bottom + space.xl, gap: space.lg }}>
        {!session ? (
          <Animated.View entering={FadeInDown} style={{ gap: space.lg }}>
            <Text style={s.lead}>Set up your phone side-on at the nets. Your coach gives you a target, you bowl, it watches and talks you through every ball.</Text>
            <Text style={s.label}>TODAY'S FOCUS</Text>
            <View style={s.focusRow}>
              {FOCUSES.map((f) => (
                <Pressable key={f} testID={`session-focus-${f.toLowerCase().replace(" ", "-")}`} onPress={() => setFocus(f)} style={[s.chip, f === focus && s.chipActive]}>
                  <Text style={[s.chipText, f === focus && { color: colors.onBrandPrimary }]}>{f}</Text>
                </Pressable>
              ))}
            </View>
            {canRecord && permission && !permission.granted ? (
              <View style={s.permCard} testID="session-camera-permission">
                <Ionicons name="camera" size={22} color={colors.accent} />
                <View style={{ flex: 1, gap: space.sm }}>
                  <Text style={s.permTitle}>Camera needed to film each ball</Text>
                  <Text style={s.lead}>{permission.canAskAgain ? "Allow the camera so your coach can watch every delivery." : "Camera access is off. Enable it in Settings."}</Text>
                  <PrimaryButton
                    testID={permission.canAskAgain ? "session-allow-camera" : "session-open-settings"}
                    label={permission.canAskAgain ? "Allow Camera" : "Open Settings"}
                    onPress={() => (permission.canAskAgain ? requestPermission() : Linking.openSettings())}
                  />
                </View>
              </View>
            ) : null}
            <PrimaryButton testID="session-start-button" label="Start Session" icon="mic" loading={busy === "starting"} onPress={start} />
          </Animated.View>
        ) : (
          <>
            {!ended ? (
              <View style={s.stageBar} testID="session-stage-bar">
                {STAGES.map((st, i) => (
                  <View key={st.key} style={{ flex: 1, gap: 4 }}>
                    <View style={[s.stageSeg, i <= stageIdx && { backgroundColor: colors.accent }]} />
                    <Text style={[s.stageLabel, i === stageIdx && { color: colors.onSurface }]} numberOfLines={1}>{st.label}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {!ended && stage === "warm_up" ? (
              <PlanStage stageKey="warm_up" title="Warm-up" subtitle="Raise temperature and mobilise before any fast bowling." items={plan.warm_up ?? []} nextLabel="Start drills" onNext={() => advance("drills")} />
            ) : null}
            {!ended && stage === "drills" ? (
              <PlanStage stageKey="drills" title="Technique Drills" subtitle={`Targeting today's focus: ${session.focus}.`} items={plan.drills ?? []} nextLabel="Start bowling block" onNext={() => advance("bowling")} />
            ) : null}
            {!ended && stage === "cool_down" ? (
              <PlanStage stageKey="cool_down" title="Cool-down" subtitle="Bring the heart rate down and restore range of motion." items={plan.cool_down ?? []} nextLabel="Finish session" onNext={end} />
            ) : null}
            {!ended && isBowl ? (
              <View style={s.blockCard} testID={`session-block-${stage}`}>
                <View style={{ flex: 1 }}>
                  <Text style={s.blockTitle}>{stage === "test" ? plan.test?.name ?? "Skills Test" : "Bowling Block"}</Text>
                  <Text style={s.blockSub}>
                    {blockBalls.length}/{stage === "test" ? plan.test?.balls ?? 6 : plan.bowling?.balls ?? 6} balls
                    {stage === "test" && plan.test?.target ? ` · Success: ${plan.test.target}` : ""}
                  </Text>
                </View>
                <Pressable testID="session-finish-block" style={s.blockBtn} disabled={!!busy || recording} onPress={() => advance(stage === "test" ? "cool_down" : "test")}>
                  <Text style={s.blockBtnText}>{stage === "test" ? "To cool-down" : "To test"}</Text>
                </Pressable>
              </View>
            ) : null}

            {!ended && isBowl ? (
              canRecord && permission?.granted ? (
                <View style={s.camBox}>
                  <CameraView ref={camRef} style={{ flex: 1 }} mode="video" facing="back" mute />
                  {recording ? (
                    <View style={s.rec} testID="session-recording-indicator">
                      <View style={s.recDot} />
                      <Text style={s.recText}>REC</Text>
                    </View>
                  ) : null}
                </View>
              ) : (
                <View style={[s.camBox, s.camPlaceholder]}>
                  <Ionicons name="videocam-off" size={28} color={colors.muted} />
                  <Text style={s.lead}>{canRecord ? "Camera not available — upload each ball clip instead." : "Live camera works in the mobile app. Upload a clip of each ball here."}</Text>
                </View>
              )
            ) : null}

            {busy === "watching" || busy === "ending" ? (
              <View style={s.coachCard} testID="session-coach-thinking">
                <ActivityIndicator color={colors.accent} />
                <Text style={s.coachText}>{busy === "watching" ? "Coach is watching that ball…" : "Wrapping up your session…"}</Text>
              </View>
            ) : message ? (
              <Animated.View key={message.text} entering={FadeInDown} style={s.coachCard} testID="session-coach-message">
                <View style={s.coachHead}>
                  <View style={s.coachAvatar}><Ionicons name="mic" size={16} color={colors.onBrandPrimary} /></View>
                  <Text style={s.coachName}>Coach</Text>
                  {message.audio ? (
                    <Pressable testID="session-replay-voice" hitSlop={12} onPress={() => say(message.audio)} style={s.replay}>
                      <Ionicons name="volume-high" size={18} color={colors.accent} />
                    </Pressable>
                  ) : null}
                </View>
                <Text style={s.coachText}>{message.text}</Text>
                {message.target ? (
                  <View style={s.target}>
                    <Text style={s.targetLabel}>NEXT BALL</Text>
                    <Text style={s.targetText} testID="session-next-target">{message.target}</Text>
                  </View>
                ) : null}
              </Animated.View>
            ) : null}

            {error ? <ErrorBanner testID="session-error" message={error} /> : null}

            {!ended && isBowl ? (
              <View style={s.actions}>
                {canRecord && permission?.granted ? (
                  <Pressable testID="session-record-button" onPress={toggleRecord} disabled={!!busy} style={[s.recordBtn, !!busy && { opacity: 0.4 }]}>
                    <View style={recording ? s.stopInner : s.recordInner} />
                  </Pressable>
                ) : null}
                <PrimaryButton testID="session-upload-ball" label="Upload ball clip" icon="cloud-upload" variant="secondary" disabled={!!busy || recording} onPress={uploadClip} />
              </View>
            ) : null}

            {balls.length ? (
              <View style={s.stats}>
                <View style={s.stat}><Text style={s.statValue} testID="session-ball-count">{balls.length}</Text><Text style={s.statLabel}>Balls</Text></View>
                <View style={s.stat}><Text style={[s.statValue, { color: scoreColor(avg, colors) }]}>{avg.toFixed(1)}</Text><Text style={s.statLabel}>Avg score</Text></View>
                <View style={s.stat}><Text style={s.statValue}>{targetHits}/{balls.length}</Text><Text style={s.statLabel}>Targets hit</Text></View>
              </View>
            ) : null}

            {balls.slice().reverse().map((b) => (
              <View key={b.n} style={s.ballRow} testID={`session-ball-${b.n}`}>
                <Text style={[s.ballScore, { color: scoreColor(b.score, colors) }]}>{b.score.toFixed(1)}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={s.ballTitle}>Ball {b.n}{b.pace_kmh ? ` · ~${b.pace_kmh} km/h` : ""}</Text>
                  <Text style={s.ballBody} numberOfLines={2}>{b.fault || b.good}</Text>
                </View>
              </View>
            ))}

            {ended ? (
              <View style={{ gap: space.md }} testID="session-summary">
                {session.test_result?.balls ? (
                  <View style={s.blockCard} testID="session-test-result">
                    <View style={{ flex: 1 }}>
                      <Text style={s.blockTitle}>{session.test_result.name}</Text>
                      <Text style={s.blockSub}>{session.test_result.hits}/{session.test_result.balls} on target · avg {session.test_result.avg_score}{session.test_result.top_pace ? ` · top ~${session.test_result.top_pace} km/h` : ""}</Text>
                    </View>
                  </View>
                ) : null}
                {(session.achievements ?? []).length ? (
                  <View style={{ gap: space.sm }}>
                    <Text style={s.label}>ACHIEVEMENTS</Text>
                    {session.achievements!.map((a) => (
                      <View key={a.key} style={s.achievement} testID={`achievement-${a.key}`}>
                        <View style={s.badge}><Ionicons name="ribbon" size={16} color={colors.accent} /></View>
                        <View style={{ flex: 1 }}>
                          <Text style={s.ballTitle}>{a.title}</Text>
                          <Text style={s.ballBody}>{a.description}</Text>
                        </View>
                      </View>
                    ))}
                  </View>
                ) : null}
                {(plan.tips ?? []).length ? (
                  <View style={{ gap: space.sm }}>
                    <Text style={s.label}>TIPS</Text>
                    {plan.tips!.map((t, i) => <Text key={i} style={s.lead}>• {t}</Text>)}
                  </View>
                ) : null}
                <PrimaryButton testID="session-done-button" label="Done" icon="checkmark" onPress={back} />
              </View>
            ) : null}
          </>
        )}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: space.lg, paddingBottom: space.sm, borderBottomWidth: 1, borderBottomColor: c.divider },
  headerTitle: { fontFamily: fonts.display, fontSize: 15, color: c.onSurface, textTransform: "uppercase", letterSpacing: 2.5 },
  headerSub: { fontFamily: fonts.text, fontSize: 11, color: c.muted },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  endBtn: { height: 44, paddingHorizontal: space.lg, borderRadius: 22, backgroundColor: c.error, justifyContent: "center" },
  endText: { fontFamily: fonts.textBold, fontSize: 14, color: c.onError },
  lead: { fontFamily: fonts.text, fontSize: 14, lineHeight: 20, color: c.onSurfaceTertiary },
  label: { fontFamily: fonts.textXBold, fontSize: 12, color: c.muted, letterSpacing: 1.5 },
  focusRow: { flexDirection: "row", flexWrap: "wrap", gap: space.sm },
  chip: { height: 44, paddingHorizontal: space.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: c.border, backgroundColor: c.surfaceSecondary, justifyContent: "center" },
  chipActive: { backgroundColor: c.brandPrimary, borderColor: c.accentLine },
  chipText: { fontFamily: fonts.textBold, fontSize: 14, color: c.onSurfaceTertiary },
  permCard: { flexDirection: "row", gap: space.md, padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.borderStrong },
  permTitle: { fontFamily: fonts.textXBold, fontSize: 15, color: c.onSurface },
  camBox: { height: 340, borderRadius: radius.lg, overflow: "hidden", backgroundColor: c.surfaceSecondary },
  camPlaceholder: { alignItems: "center", justifyContent: "center", gap: space.sm, padding: space.xl, height: 180 },
  rec: { position: "absolute", top: space.md, left: space.md, flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: c.scrim, paddingHorizontal: space.md, paddingVertical: 6, borderRadius: radius.pill },
  recDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: c.error },
  recText: { fontFamily: fonts.textXBold, fontSize: 12, color: c.onSurface, letterSpacing: 1 },
  coachCard: { padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.md },
  coachHead: { flexDirection: "row", alignItems: "center", gap: space.sm },
  coachAvatar: { width: 28, height: 28, borderRadius: 14, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  coachName: { flex: 1, fontFamily: fonts.textXBold, fontSize: 14, color: c.onSurface },
  replay: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  coachText: { fontFamily: fonts.text, fontSize: 15, lineHeight: 22, color: c.onSurfaceSecondary },
  target: { padding: space.md, borderRadius: radius.md, backgroundColor: c.brandTertiary, gap: 4 },
  targetLabel: { fontFamily: fonts.textXBold, fontSize: 11, color: c.accent, letterSpacing: 1.5 },
  targetText: { fontFamily: fonts.textBold, fontSize: 15, color: c.onSurface },
  actions: { alignItems: "center", gap: space.md },
  recordBtn: { width: 80, height: 80, borderRadius: 40, borderWidth: 4, borderColor: c.onSurface, alignItems: "center", justifyContent: "center" },
  recordInner: { width: 60, height: 60, borderRadius: 30, backgroundColor: c.error },
  stopInner: { width: 30, height: 30, borderRadius: radius.sm, backgroundColor: c.error },
  stats: { flexDirection: "row", gap: space.sm },
  stat: { flex: 1, padding: space.md, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary },
  statValue: { fontFamily: fonts.display, fontSize: 28, color: c.onSurface },
  statLabel: { fontFamily: fonts.text, fontSize: 12, color: c.muted },
  ballRow: { flexDirection: "row", alignItems: "center", gap: space.md, padding: space.md, borderRadius: radius.md, backgroundColor: c.surfaceSecondary },
  ballScore: { fontFamily: fonts.display, fontSize: 26, width: 48 },
  ballTitle: { fontFamily: fonts.textBold, fontSize: 14, color: c.onSurface },
  ballBody: { fontFamily: fonts.text, fontSize: 12, color: c.muted },
  stageBar: { flexDirection: "row", gap: 4 },
  stageSeg: { height: 3, borderRadius: 2, backgroundColor: c.surfaceTertiary },
  stageLabel: { fontFamily: fonts.textBold, fontSize: 10, color: c.muted },
  blockCard: { flexDirection: "row", alignItems: "center", gap: space.md, padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.accentLine },
  blockTitle: { fontFamily: fonts.display, fontSize: 16, color: c.onSurface },
  blockSub: { fontFamily: fonts.mono, fontSize: 12, color: c.onSurfaceTertiary, marginTop: 2 },
  blockBtn: { height: 44, paddingHorizontal: space.md, borderRadius: radius.md, backgroundColor: c.surfaceTertiary, justifyContent: "center" },
  blockBtnText: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurface },
  achievement: { flexDirection: "row", alignItems: "center", gap: space.md, padding: space.md, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border },
  badge: { width: 36, height: 36, borderRadius: 18, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
}));
