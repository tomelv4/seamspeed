import { useQueryClient } from "@tanstack/react-query";
import { Image } from "expo-image";
import * as ImagePicker from "expo-image-picker";
import { useRouter } from "expo-router";
import { useState } from "react";
import { Linking, Text, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import Animated, { FadeIn, FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { uploadDelivery, useAnalyses, type AnalysisProgress } from "@/src/api";
import { useSubscription } from "@/src/revenuecat";
import { IMAGES, fonts, radius, space } from "@/src/constants";
import { ErrorBanner, Ionicons, PressScale, PrimaryButton } from "@/src/components/ui";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme } from "@/src/theme";

type Picked = { uri: string; name?: string; mimeType?: string; duration?: number | null; size?: number };
type PermState = "idle" | "explain" | "blocked";

 const MAX_BYTES = 60 * 1024 * 1024;

export default function Analyze() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const qc = useQueryClient();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const [video, setVideo] = useState<Picked | null>(null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<AnalysisProgress>({ stage: "uploading", percent: 0, message: "Uploading your video" });
  const [error, setError] = useState<string | null>(null);
  const [perm, setPerm] = useState<PermState>("idle");
  const { isSubscribed, isLoading: subLoading } = useSubscription();
  const analyses = useAnalyses();
  const freeUsed = !subLoading && !isSubscribed && (analyses.data ?? []).filter((x) => x.is_bowling_video).length >= 1;
  const gate = (fn: () => void) => (subLoading || analyses.isLoading ? undefined : freeUsed ? router.push("/paywall") : fn());

  const accept = (res: ImagePicker.ImagePickerResult) => {
    if (res.canceled || !res.assets?.[0]) return;
    const a = res.assets[0];
    if (a.fileSize && a.fileSize > MAX_BYTES) {
      setError("Clip is too large. Trim it to a single delivery (under ~15 seconds).");
      return;
    }
    setError(null);
    setVideo({ uri: a.uri, name: a.fileName ?? "delivery.mp4", mimeType: a.mimeType ?? "video/mp4", duration: a.duration, size: a.fileSize });
  };

  const pickFromLibrary = async () => {
    accept(await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["videos"], quality: 0.7, videoMaxDuration: 20 }));
  };

  const launchCamera = async () => {
    accept(await ImagePicker.launchCameraAsync({ mediaTypes: ["videos"], videoMaxDuration: 15, videoQuality: ImagePicker.UIImagePickerControllerQualityType.Medium }));
  };

  const recordPressed = async () => {
    const current = await ImagePicker.getCameraPermissionsAsync();
    if (current.granted) return launchCamera();
    setPerm(current.canAskAgain ? "explain" : "blocked");
  };

  const requestCamera = async () => {
    const res = await ImagePicker.requestCameraPermissionsAsync();
    if (res.granted) {
      setPerm("idle");
      return launchCamera();
    }
    setPerm(res.canAskAgain ? "explain" : "blocked");
  };

  const analyze = async () => {
    if (!video) return;
    if (freeUsed) return router.push("/paywall");
    setBusy(true);
    setError(null);
    setProgress({ stage: "uploading", percent: 0, message: "Uploading your video" });
    try {
      const result = await uploadDelivery(video, notes.trim(), setProgress);
      qc.invalidateQueries();
      setVideo(null);
      setNotes("");
      router.push(`/report/${result.id}`);
    } catch (e: any) {
      setError(e?.message ?? "Analysis failed. Please ensure the video is clear and side-on.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={s.screen}>
      <View style={[s.header, { paddingTop: insets.top + space.sm }]}>
        <Text style={s.title}>Analyze</Text>
        <Text style={s.subtitle}>AI breakdown of one delivery</Text>
      </View>

      <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ padding: space.lg, paddingBottom: bottomChrome + space.xl, gap: space.lg }}>
        {busy ? (
          <Animated.View entering={FadeIn} style={s.busyCard} testID="analysis-progress">
            <Text style={s.busyTitle}>Analyzing delivery…</Text>
            <Text style={s.busyBody}>{progress.message ?? "Processing your bowling video"}</Text>
            <View style={s.progressTrack}>
              <View style={[s.progressFill, { width: `${Math.max(0, Math.min(100, progress.percent ?? 0))}%` }]} />
            </View>
            <Text style={s.progressMeta}>{Math.round(progress.percent ?? 0)}% · {progress.stage ?? "processing"}</Text>
          </Animated.View>
        ) : video ? (
          <Animated.View entering={FadeInDown} style={s.previewCard} testID="video-selected-card">
            <View style={s.previewIcon}>
              <Ionicons name="film" size={28} color={colors.accent} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.previewTitle} numberOfLines={1}>{video.name}</Text>
              <Text style={s.previewMeta}>
                {video.duration ? `${(video.duration / 1000).toFixed(1)}s` : "Video"}{video.size ? ` · ${(video.size / 1048576).toFixed(1)} MB` : ""}
              </Text>
            </View>
            <PressScale testID="remove-video-button" style={s.iconBtn} onPress={() => setVideo(null)}>
              <Ionicons name="close" size={20} color={colors.onSurface} />
            </PressScale>
          </Animated.View>
        ) : (
          <Animated.View entering={FadeInDown} style={s.drop}>
            <Image source={{ uri: IMAGES.analyze }} style={s.dropImg} contentFit="cover" />
            <View style={s.dropOverlay}>
              <View style={s.frame} />
              <Text style={s.dropText}>Side-on view · full run-up to follow-through</Text>
            </View>
          </Animated.View>
        )}

        {perm !== "idle" && !busy ? (
          <View style={s.permCard} testID="camera-permission-card">
            <Ionicons name="camera" size={22} color={colors.accent} />
            <View style={{ flex: 1, gap: space.sm }}>
              <Text style={s.permTitle}>Camera access needed</Text>
              <Text style={s.permBody}>
                {perm === "blocked"
                  ? "Camera access is off. Enable it in Settings to record deliveries, or upload from your library."
                  : "Allow the camera to film your delivery so the AI can analyse your action."}
              </Text>
              <View style={{ flexDirection: "row", gap: space.sm }}>
                {perm === "blocked" ? (
                  <PressScale testID="open-settings-button" style={s.smallBtn} onPress={() => Linking.openSettings()}>
                    <Text style={s.smallBtnText}>Open Settings</Text>
                  </PressScale>
                ) : (
                  <PressScale testID="allow-camera-button" style={s.smallBtn} onPress={requestCamera}>
                    <Text style={s.smallBtnText}>Allow Camera</Text>
                  </PressScale>
                )}
                <PressScale testID="dismiss-permission-button" style={[s.smallBtn, s.smallBtnGhost]} onPress={() => setPerm("idle")}>
                  <Text style={[s.smallBtnText, { color: colors.onSurface }]}>Not now</Text>
                </PressScale>
              </View>
            </View>
          </View>
        ) : null}

        {error ? <ErrorBanner testID="analysis-error" message={error} /> : null}

        {!busy && !video ? (
          <View style={{ gap: space.md }}>
            {freeUsed ? (
              <PressScale testID="free-used-banner" style={s.freeBanner} onPress={() => router.push("/paywall")}>
                <Ionicons name="lock-closed" size={18} color={colors.accent} />
                <Text style={s.freeText}>Your free analysis is used. Go Pro for unlimited analyses.</Text>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </PressScale>
            ) : !isSubscribed ? (
              <Text style={s.freeHint} testID="free-analysis-hint">1 free analysis included · then Pro</Text>
            ) : null}
            <PrimaryButton testID="record-video-button" label="Record Delivery" icon="videocam" onPress={() => gate(recordPressed)} />
            <PrimaryButton testID="upload-video-button" label="Upload from Library" icon="images" variant="secondary" onPress={() => gate(pickFromLibrary)} />
          </View>
        ) : null}

        {!busy && video ? (
          <View style={{ gap: space.md }}>
            <Text style={s.label}>Notes for the coach (optional)</Text>
            <TextInput
              testID="analysis-notes-input"
              style={s.input}
              placeholder="e.g. Trying to bowl an outswinger, felt my front knee collapse"
              placeholderTextColor={colors.muted}
              value={notes}
              onChangeText={setNotes}
              multiline
              maxLength={300}
            />
            <PrimaryButton testID="analyze-delivery-button" label="Analyze Delivery" icon="sparkles" onPress={analyze} />
          </View>
        ) : null}

        {!busy ? (
          <View style={s.tips}>
            <Text style={s.tipsTitle}>FILMING TIPS</Text>
            {[
              ["phone-landscape", "Film side-on from square leg, phone steady"],
              ["walk", "Capture the full run-up through follow-through"],
              ["sunny", "Good light, one bowler in frame"],
              ["timer", "One delivery per clip, 5-15 seconds"],
            ].map(([icon, text]) => (
              <View key={text} style={s.tipRow}>
                <Ionicons name={icon as any} size={18} color={colors.accent} />
                <Text style={s.tipText}>{text}</Text>
              </View>
            ))}
          </View>
        ) : null}
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: space.lg, paddingBottom: space.md, borderBottomWidth: 1, borderBottomColor: c.divider },
  title: { fontFamily: fonts.display, fontSize: 24, color: c.onSurface, textTransform: "uppercase", letterSpacing: 2 },
  subtitle: { fontFamily: fonts.text, fontSize: 13, color: c.muted },
  drop: { height: 260, borderRadius: radius.lg, overflow: "hidden", backgroundColor: c.surfaceSecondary },
  dropImg: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, opacity: 0.45 },
  dropOverlay: { flex: 1, alignItems: "center", justifyContent: "center", padding: space.lg, gap: space.md },
  frame: { width: "70%", height: 150, borderWidth: 2, borderStyle: "dashed", borderColor: c.accentLine, borderRadius: radius.md },
  dropText: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurface, textAlign: "center" },
  previewCard: { flexDirection: "row", alignItems: "center", gap: space.md, padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.accentLine },
  previewIcon: { width: 56, height: 56, borderRadius: radius.md, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  previewTitle: { fontFamily: fonts.textBold, fontSize: 15, color: c.onSurface },
  previewMeta: { fontFamily: fonts.text, fontSize: 12, color: c.muted, marginTop: 2 },
  iconBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  busyCard: { padding: space.xl, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, gap: space.md },
  busyTitle: { fontFamily: fonts.display, fontSize: 28, color: c.onSurface, textTransform: "uppercase" },
  busyBody: { fontFamily: fonts.text, fontSize: 13, color: c.muted, marginBottom: space.sm },
  progressTrack: { height: 7, borderRadius: 4, backgroundColor: c.surfaceTertiary, overflow: "hidden" },
  progressFill: { height: 7, borderRadius: 4, backgroundColor: c.accent },
  progressMeta: { fontFamily: fonts.mono, fontSize: 11, color: c.muted, textAlign: "right" },
  label: { fontFamily: fonts.textBold, fontSize: 13, color: c.onSurfaceTertiary },
  input: { minHeight: 90, borderRadius: radius.md, backgroundColor: c.surfaceTertiary, color: c.onSurface, padding: space.md, fontFamily: fonts.text, fontSize: 14, textAlignVertical: "top", borderWidth: 1, borderColor: c.border },
  permCard: { flexDirection: "row", gap: space.md, padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.borderStrong },
  permTitle: { fontFamily: fonts.textXBold, fontSize: 15, color: c.onSurface },
  permBody: { fontFamily: fonts.text, fontSize: 13, color: c.muted, lineHeight: 19 },
  smallBtn: { minHeight: 44, paddingHorizontal: space.lg, borderRadius: radius.pill, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  smallBtnGhost: { backgroundColor: c.surfaceTertiary },
  smallBtnText: { fontFamily: fonts.textBold, fontSize: 13, color: c.onBrandPrimary },
  tips: { padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, gap: space.md },
  freeBanner: { flexDirection: "row", alignItems: "center", gap: space.md, padding: space.lg, borderRadius: radius.lg, backgroundColor: c.brandTertiary, borderWidth: 1, borderColor: c.accentLine },
  freeText: { flex: 1, fontFamily: fonts.textBold, fontSize: 13, color: c.onSurface },
  freeHint: { fontFamily: fonts.textBold, fontSize: 12, color: c.muted, textAlign: "center" },
  tipsTitle: { fontFamily: fonts.textXBold, fontSize: 12, color: c.muted, letterSpacing: 1.5 },
  tipRow: { flexDirection: "row", alignItems: "center", gap: space.md },
  tipText: { flex: 1, fontFamily: fonts.text, fontSize: 13, color: c.onSurfaceSecondary },
}));
