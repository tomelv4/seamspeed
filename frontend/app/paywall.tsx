import { useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, Text, View } from "react-native";
import type { PurchasesPackage } from "react-native-purchases";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { fonts, radius, space } from "@/src/constants";
import { ErrorBanner, Ionicons, PressScale, PrimaryButton } from "@/src/components/ui";
import { isTestStore, useSubscription } from "@/src/revenuecat";
import { makeStyles, useTheme } from "@/src/theme";

const FEATURES: [string, string][] = [
  ["body", "27-step biomechanics breakdown with skeleton tracking"],
  ["mic", "Live ball-by-ball sessions with a spoken AI coach"],
  ["infinite", "Unlimited delivery analyses"],
  ["chatbubbles", "ChatGPT coach chat for pace, swing & injury prevention"],
  ["barbell", "Personalised drills for your faults"],
  ["stats-chart", "Pace, score & fault progress tracking"],
];

export default function Paywall() {
  const s = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { offerings, isSubscribed, identityReady, identityError, isLoading, purchase, restore, isPurchasing, isRestoring } = useSubscription();
  const packages = offerings?.current?.availablePackages ?? [];
  const [selected, setSelected] = useState<PurchasesPackage | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  useEffect(() => {
    if (!selected && packages.length) setSelected(packages.find((p) => p.packageType === "ANNUAL") ?? packages[0]);
  }, [packages, selected]);

  const close = () => (router.canGoBack() ? router.back() : router.replace("/"));

  const buy = async () => {
    if (!selected) return;
    setConfirm(false);
    setError(null);
    try {
      await purchase(selected);
      close();
    } catch (e: any) {
      if (e?.userCancelled) return;
      setError(e?.message === "identity_not_ready" ? "Account not ready yet, please try again in a moment." : e?.message ?? "Purchase failed");
    }
  };

  const onRestore = async () => {
    setError(null);
    try {
      const info2 = await restore();
      setInfo(info2.entitlements.active.pro ? "Pro restored!" : "No previous purchases found.");
    } catch (e: any) {
      setError(e?.message ?? "Restore failed");
    }
  };

  const monthly = packages.find((p) => p.packageType === "MONTHLY");
  const savePct = (p: PurchasesPackage) =>
    p.packageType === "ANNUAL" && monthly ? Math.round((1 - p.product.price / (monthly.product.price * 12)) * 100) : 0;

  const freeTrial = (p: PurchasesPackage) => {
    const prod: any = p.product;
    const phase = prod.introPrice ?? prod.defaultOption?.freePhase ?? prod.trial ?? null;
    if (!phase) return null;
    const unit = String(phase.periodUnit ?? phase.period ?? "").toUpperCase();
    const n = phase.periodNumberOfUnits ?? phase.cycles ?? 1;
    return unit.includes("W") || unit === "P1W" ? `${n * 7}-day free trial` : unit.includes("D") ? `${n}-day free trial` : "Free trial";
  };

  return (
    <View style={s.screen}>
      <ScrollView contentContainerStyle={{ padding: space.lg, paddingTop: insets.top + space.md, paddingBottom: insets.bottom + space.xl, gap: space.lg }}>
        <PressScale testID="paywall-close-button" style={s.close} onPress={close}>
          <Ionicons name="close" size={22} color={colors.onSurface} />
        </PressScale>
        <Text style={s.kicker}>PACED PRO</Text>
        <Text style={s.title}>Engineered{"\n"}for pace.</Text>
        <Text style={s.sub}>Unlock the full AI coaching suite. Your first analysis is free — everything else is Pro.</Text>

        <View style={{ gap: space.md }}>
          {FEATURES.map(([icon, text]) => (
            <View key={text} style={s.feature}>
              <View style={s.featureIcon}><Ionicons name={icon as any} size={18} color={colors.accent} /></View>
              <Text style={s.featureText}>{text}</Text>
            </View>
          ))}
        </View>

        {isSubscribed ? (
          <View style={s.proBox} testID="paywall-already-pro">
            <Ionicons name="checkmark-circle" size={24} color={colors.success} />
            <Text style={s.featureText}>You're Pro. Everything is unlocked.</Text>
          </View>
        ) : isLoading ? (
          <ActivityIndicator color={colors.accent} />
        ) : packages.length === 0 ? (
          <ErrorBanner testID="paywall-unavailable" message="Subscription options are unavailable right now. Please try again later." />
        ) : (
          <View style={{ gap: space.md }}>
            {packages.map((p) => {
              const active = selected?.identifier === p.identifier;
              const save = savePct(p);
              return (
                <Pressable key={p.identifier} testID={`paywall-package-${p.packageType.toLowerCase()}`} onPress={() => setSelected(p)} style={[s.pkg, active && s.pkgActive]}>
                  <Ionicons name={active ? "radio-button-on" : "radio-button-off"} size={22} color={active ? colors.accent : colors.muted} />
                  <View style={{ flex: 1 }}>
                    <Text style={s.pkgTitle}>{p.packageType === "ANNUAL" ? "Yearly" : p.packageType === "MONTHLY" ? "Monthly" : p.product.title}</Text>
                    <Text style={s.pkgSub}>{p.packageType === "ANNUAL" ? `${freeTrial(p) ? `${freeTrial(p)} · ` : ""}${p.product.pricePerMonthString ?? ""} / month, billed yearly` : "Billed monthly, cancel anytime"}</Text>
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={s.price}>{p.product.priceString}</Text>
                    {save > 0 ? <Text style={s.save}>SAVE {save}%</Text> : null}
                  </View>
                </Pressable>
              );
            })}
          </View>
        )}

        {identityError ? <ErrorBanner testID="paywall-identity-error" message={`Purchases unavailable: ${identityError}`} /> : null}
        {error ? <ErrorBanner testID="paywall-error" message={error} /> : null}
        {info ? <Text style={s.info} testID="paywall-info">{info}</Text> : null}

        {!isSubscribed && packages.length > 0 ? (
          <PrimaryButton
            testID="paywall-subscribe-button"
            label={selected && freeTrial(selected) ? "Start free trial" : "Continue"}
            icon="flash"
            disabled={!selected || !identityReady}
            loading={isPurchasing}
            onPress={() => (isTestStore ? setConfirm(true) : buy())}
          />
        ) : null}
        <Pressable testID="paywall-restore-button" onPress={onRestore} style={s.restore} disabled={isRestoring}>
          <Text style={s.restoreText}>{isRestoring ? "Restoring…" : "Restore purchases"}</Text>
        </Pressable>
        <Text style={s.legal}>Subscriptions renew automatically until cancelled in your store account settings.</Text>
      </ScrollView>

      <Modal transparent visible={confirm} animationType="fade" onRequestClose={() => setConfirm(false)}>
        <View style={s.modalBg}>
          <View style={s.modal} testID="paywall-confirm-modal">
            <Text style={s.modalTitle}>Test purchase</Text>
            <Text style={s.sub}>Simulated purchase in the RevenueCat Test Store — no real money is charged.</Text>
            <Text style={s.featureText}>{selected?.product.priceString} · {selected?.packageType === "ANNUAL" ? "Yearly" : "Monthly"}</Text>
            <PrimaryButton testID="paywall-confirm-buy" label="Confirm" onPress={buy} />
            <PrimaryButton testID="paywall-cancel-buy" label="Cancel" variant="secondary" onPress={() => setConfirm(false)} />
          </View>
        </View>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  screen: { flex: 1, backgroundColor: c.surface },
  close: { alignSelf: "flex-end", width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  kicker: { fontFamily: fonts.textXBold, fontSize: 12, color: c.accent, letterSpacing: 2 },
  title: { fontFamily: fonts.display, fontSize: 34, lineHeight: 40, color: c.onSurface, letterSpacing: -0.5 },
  sub: { fontFamily: fonts.text, fontSize: 14, lineHeight: 20, color: c.muted },
  feature: { flexDirection: "row", alignItems: "center", gap: space.md },
  featureIcon: { width: 36, height: 36, borderRadius: 18, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  featureText: { flex: 1, fontFamily: fonts.textBold, fontSize: 14, color: c.onSurface },
  proBox: { flexDirection: "row", gap: space.md, alignItems: "center", padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary },
  pkg: { flexDirection: "row", alignItems: "center", gap: space.md, padding: space.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1.5, borderColor: c.border },
  pkgActive: { borderColor: c.accentLine },
  pkgTitle: { fontFamily: fonts.textXBold, fontSize: 16, color: c.onSurface },
  pkgSub: { fontFamily: fonts.text, fontSize: 12, color: c.muted, marginTop: 2 },
  price: { fontFamily: fonts.display, fontSize: 24, color: c.onSurface },
  save: { fontFamily: fonts.textXBold, fontSize: 10, color: c.success, letterSpacing: 1 },
  info: { fontFamily: fonts.textBold, fontSize: 13, color: c.success, textAlign: "center" },
  restore: { alignSelf: "center", minHeight: 44, justifyContent: "center" },
  restoreText: { fontFamily: fonts.textBold, fontSize: 14, color: c.onSurfaceTertiary, textDecorationLine: "underline" },
  legal: { fontFamily: fonts.text, fontSize: 11, color: c.muted, textAlign: "center" },
  modalBg: { flex: 1, backgroundColor: c.scrim, justifyContent: "center", padding: space.xl },
  modal: { backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, padding: space.xl, gap: space.md, borderWidth: 1, borderColor: c.border },
  modalTitle: { fontFamily: fonts.display, fontSize: 26, color: c.onSurface, textTransform: "uppercase" },
}));
