import Ionicons, { IoniconsIconName } from "@react-native-vector-icons/ionicons";
import * as Haptics from "expo-haptics";
import React from "react";
import { ActivityIndicator, Image, Platform, Pressable, PressableProps, StyleProp, Text, View, ViewStyle } from "react-native";
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from "react-native-reanimated";

import { fonts, radius, space } from "@/src/constants";
import { makeStyles, useTheme } from "@/src/theme";

export { Ionicons };
export type IconName = IoniconsIconName;

type PressProps = PressableProps & { style?: StyleProp<ViewStyle>; children: React.ReactNode };

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

export function PressScale({ style, children, onPress, ...rest }: PressProps) {
  const scale = useSharedValue(1);
  const anim = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  return (
    <AnimatedPressable
      {...rest}
      style={[style, anim]}
      onPressIn={() => (scale.value = withSpring(0.97, { damping: 20 }))}
      onPressOut={() => (scale.value = withSpring(1, { damping: 20 }))}
      onPress={(e) => {
        if (Platform.OS !== "web") Haptics.selectionAsync();
        onPress?.(e);
      }}
    >
      {children}
    </AnimatedPressable>
  );
}

export function PrimaryButton({
  label, icon, onPress, loading, disabled, testID, variant = "primary",
}: {
  label: string; icon?: IconName; onPress: () => void; loading?: boolean; disabled?: boolean; testID: string;
  variant?: "primary" | "secondary";
}) {
  const s = useStyles();
  const { colors } = useTheme();
  const primary = variant === "primary";
  const fg = primary ? colors.onBrandPrimary : colors.onSurface;
  return (
    <PressScale
      testID={testID}
      onPress={onPress}
      disabled={disabled || loading}
      style={[s.btn, primary ? s.btnPrimary : s.btnSecondary, (disabled || loading) && { opacity: 0.5 }]}
    >
      {loading ? <ActivityIndicator color={fg} /> : icon ? <Ionicons name={icon} size={20} color={fg} /> : null}
      <Text style={[s.btnText, { color: fg }]}>{label}</Text>
    </PressScale>
  );
}

export function Wordmark({ size = 24 }: { size?: number }) {
  const h = size * 1.25;
  return (
    <Image
      testID="app-wordmark"
      accessibilityLabel="PACED"
      source={require("../../assets/images/paced-wordmark.png")}
      style={{ height: h, width: h * (1362 / 295), borderRadius: 4 }}
      resizeMode="contain"
    />
  );
}

export function SectionTitle({ title, action, onAction, testID }: { title: string; action?: string; onAction?: () => void; testID?: string }) {
  const s = useStyles();
  return (
    <View style={s.sectionRow}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: space.sm }}>
        <View style={s.tick} />
        <Text style={s.sectionTitle}>{title}</Text>
      </View>
      {action ? (
        <Pressable testID={testID} onPress={onAction} hitSlop={12}>
          <Text style={s.sectionAction}>{action}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function riskColor(level: string | undefined, colors: ReturnType<typeof useTheme>["colors"]) {
  if (level === "high") return colors.error;
  if (level === "medium") return colors.warning;
  return colors.success;
}

export function scoreColor(score: number, colors: ReturnType<typeof useTheme>["colors"]) {
  if (score >= 7.5) return colors.success;
  if (score >= 5) return colors.warning;
  return colors.error;
}

export function Pill({ label, color, testID, icon }: { label: string; color: string; testID?: string; icon?: IconName }) {
  const s = useStyles();
  return (
    <View testID={testID} style={[s.pill, { borderColor: color }]}>
      {icon ? <Ionicons name={icon} size={12} color={color} /> : null}
      <Text style={[s.pillText, { color }]}>{label}</Text>
    </View>
  );
}

export function EmptyState({ icon, title, body, children, testID }: { icon: IconName; title: string; body: string; children?: React.ReactNode; testID?: string }) {
  const s = useStyles();
  const { colors } = useTheme();
  return (
    <View testID={testID} style={s.empty}>
      <View style={s.emptyIcon}>
        <Ionicons name={icon} size={32} color={colors.accent} />
      </View>
      <Text style={s.emptyTitle}>{title}</Text>
      <Text style={s.emptyBody}>{body}</Text>
      {children}
    </View>
  );
}

export function Loading({ testID }: { testID?: string }) {
  const { colors } = useTheme();
  return (
    <View testID={testID} style={{ padding: space.xxxl, alignItems: "center" }}>
      <ActivityIndicator color={colors.accent} size="large" />
    </View>
  );
}

export function ErrorBanner({ message, onRetry, testID }: { message: string; onRetry?: () => void; testID?: string }) {
  const s = useStyles();
  const { colors } = useTheme();
  return (
    <View testID={testID} style={s.errorBox}>
      <Ionicons name="alert-circle" size={20} color={colors.error} />
      <Text style={s.errorText}>{message}</Text>
      {onRetry ? (
        <Pressable onPress={onRetry} hitSlop={10} testID={testID ? `${testID}-retry` : undefined}>
          <Text style={s.sectionAction}>Retry</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function Bars({ data, max, color, height = 140, format }: {
  data: { label: string; value: number }[]; max: number; color: string; height?: number; format?: (v: number) => string;
}) {
  const s = useStyles();
  return (
    <View style={[s.bars, { height: height + 40 }]}>
      {data.map((d, i) => (
        <View key={i} style={s.barCol}>
          <Text style={s.barValue}>{format ? format(d.value) : d.value}</Text>
          <View style={[s.barTrack, { height }]}>
            <View style={[s.barFill, { height: Math.max(4, (d.value / (max || 1)) * height), backgroundColor: i === data.length - 1 ? color : `${color}80` }]} />
          </View>
          <Text style={s.barLabel} numberOfLines={1}>{d.label}</Text>
        </View>
      ))}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  btn: { minHeight: 52, borderRadius: radius.md, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: space.sm, paddingHorizontal: space.xl },
  btnPrimary: { backgroundColor: c.brandPrimary, borderWidth: 1, borderColor: c.accentLine },
  btnSecondary: { backgroundColor: c.surfaceTertiary, borderWidth: 1, borderColor: c.border },
  btnText: { fontFamily: fonts.textBold, fontSize: 15, letterSpacing: 0.8 },
  sectionRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: space.md },
  sectionTitle: { fontFamily: fonts.displaySemi, fontSize: 13, color: c.onSurfaceTertiary, textTransform: "uppercase", letterSpacing: 2.5 },
  tick: { width: 3, height: 14, borderRadius: 1, backgroundColor: c.accent },
  sectionAction: { fontFamily: fonts.textBold, fontSize: 14, color: c.accent },
  pill: { flexDirection: "row", alignItems: "center", gap: 4, borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 4, alignSelf: "flex-start" },
  pillText: { fontFamily: fonts.textBold, fontSize: 11, textTransform: "uppercase", letterSpacing: 0.6 },
  empty: { alignItems: "center", padding: space.xl, gap: space.sm, backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: c.border },
  emptyIcon: { width: 64, height: 64, borderRadius: 32, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center", marginBottom: space.sm },
  emptyTitle: { fontFamily: fonts.display, fontSize: 22, color: c.onSurface, textAlign: "center" },
  emptyBody: { fontFamily: fonts.text, fontSize: 14, color: c.muted, textAlign: "center", lineHeight: 20, marginBottom: space.sm },
  errorBox: { flexDirection: "row", alignItems: "center", gap: space.sm, padding: space.md, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.error },
  errorText: { flex: 1, fontFamily: fonts.text, fontSize: 13, color: c.onSurfaceSecondary },
  bars: { flexDirection: "row", alignItems: "flex-end", gap: space.sm },
  barCol: { flex: 1, alignItems: "center", gap: 4 },
  barTrack: { width: "100%", maxWidth: 28, justifyContent: "flex-end", backgroundColor: c.surfaceTertiary, borderRadius: radius.sm, overflow: "hidden" },
  barFill: { width: "100%", borderRadius: radius.sm },
  barValue: { fontFamily: fonts.displaySemi, fontSize: 12, color: c.onSurfaceTertiary },
  barLabel: { fontFamily: fonts.text, fontSize: 10, color: c.muted },
}));
