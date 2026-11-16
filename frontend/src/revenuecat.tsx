import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Platform } from "react-native";
import Purchases, { LOG_LEVEL } from "react-native-purchases";
import type { CustomerInfo, PurchasesPackage } from "react-native-purchases";

import { getDeviceId } from "@/src/api";
import { storage } from "@/src/utils/storage";

const REVENUECAT_TEST_API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_TEST_API_KEY;
const REVENUECAT_IOS_API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_IOS_API_KEY;
const REVENUECAT_ANDROID_API_KEY = process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY;

export const REVENUECAT_ENTITLEMENT_IDENTIFIER = "pro";
export const rcEnabled = Platform.OS !== "web" || __DEV__;
export const isTestStore = Platform.OS === "web" || __DEV__;

function getRevenueCatApiKey() {
  if (!REVENUECAT_TEST_API_KEY || !REVENUECAT_IOS_API_KEY || !REVENUECAT_ANDROID_API_KEY) {
    throw new Error("RevenueCat public API keys not found");
  }
  if (isTestStore) return REVENUECAT_TEST_API_KEY;
  if (Platform.OS === "ios") return REVENUECAT_IOS_API_KEY;
  if (Platform.OS === "android") return REVENUECAT_ANDROID_API_KEY;
  return REVENUECAT_TEST_API_KEY;
}

export function initializeRevenueCat() {
  if (!rcEnabled) return;
  Purchases.setLogLevel(__DEV__ ? LOG_LEVEL.DEBUG : LOG_LEVEL.WARN);
  Purchases.configure({ apiKey: getRevenueCatApiKey() });
}

function useSubscriptionContext() {
  const queryClient = useQueryClient();
  const [identityError, setIdentityError] = useState<string | null>(null);
  const [identityBound, setIdentityBound] = useState(false);

  // Bind RevenueCat to this app's stable user id (the device profile id used by the backend).
  useEffect(() => {
    if (!rcEnabled) return;
    (async () => {
      try {
        const id = await getDeviceId();
        const { customerInfo } = await Purchases.logIn(id);
        queryClient.setQueryData(["revenuecat", "customer-info"], customerInfo);
        setIdentityBound(true);
      } catch (e) {
        setIdentityError(String(e));
      }
    })();
  }, [queryClient]);

  const customerInfoQuery = useQuery({
    queryKey: ["revenuecat", "customer-info"],
    queryFn: () => Purchases.getCustomerInfo(),
    enabled: rcEnabled && identityBound,
    staleTime: 60 * 1000,
  });

  const offeringsQuery = useQuery({
    queryKey: ["revenuecat", "offerings"],
    queryFn: () => Purchases.getOfferings(),
    enabled: rcEnabled && identityBound,
    staleTime: 300 * 1000,
  });

  useEffect(() => {
    if (!rcEnabled) return;
    const listener = (info: CustomerInfo) => queryClient.setQueryData(["revenuecat", "customer-info"], info);
    Purchases.addCustomerInfoUpdateListener(listener);
    return () => {
      Purchases.removeCustomerInfoUpdateListener(listener);
    };
  }, [queryClient]);

  const purchaseMutation = useMutation({
    mutationFn: async (pkg: PurchasesPackage) => {
      const id = (await Purchases.getCustomerInfo()).originalAppUserId;
      if (id.startsWith("$RCAnonymousID:")) throw new Error("identity_not_ready");
      const { customerInfo } = await Purchases.purchasePackage(pkg);
      return customerInfo;
    },
  });

  const restoreMutation = useMutation({ mutationFn: () => Purchases.restorePurchases() });

  // Developer Pro unlock: only exists in development (preview / Expo Go). Store builds compile it out.
  const [devPro, setDevProState] = useState(false);
  useEffect(() => {
    if (__DEV__) storage.getItem<boolean>("dev_pro", false).then((v) => setDevProState(!!v));
  }, []);
  const setDevPro = useCallback((on: boolean) => {
    if (!__DEV__) return;
    setDevProState(on);
    storage.setItem("dev_pro", on);
  }, []);

  const paidPro = customerInfoQuery.data?.entitlements.active?.[REVENUECAT_ENTITLEMENT_IDENTIFIER] !== undefined;
  const isSubscribed = paidPro || (__DEV__ && devPro);
  const originalAppUserId = customerInfoQuery.data?.originalAppUserId;
  const identityReady = !!originalAppUserId && !originalAppUserId.startsWith("$RCAnonymousID:");

  return {
    customerInfo: customerInfoQuery.data,
    offerings: offeringsQuery.data,
    offeringsError: offeringsQuery.error,
    isSubscribed,
    devPro: __DEV__ && devPro,
    setDevPro,
    identityReady,
    identityError,
    isLoading: !identityBound && !identityError ? true : customerInfoQuery.isLoading || offeringsQuery.isLoading,
    purchase: purchaseMutation.mutateAsync,
    restore: restoreMutation.mutateAsync,
    isPurchasing: purchaseMutation.isPending,
    isRestoring: restoreMutation.isPending,
  };
}

type SubscriptionContextValue = ReturnType<typeof useSubscriptionContext>;
const Context = createContext<SubscriptionContextValue | null>(null);

export function SubscriptionProvider({ children }: { children: React.ReactNode }) {
  const value = useSubscriptionContext();
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useSubscription() {
  const ctx = useContext(Context);
  if (!ctx) throw new Error("useSubscription must be used within a SubscriptionProvider");
  return ctx;
}

/** Runs `fn` for Pro users, otherwise opens the paywall. */
export function useRequirePro() {
  const { isSubscribed } = useSubscription();
  const router = useRouter();
  return useCallback(
    (fn: () => void) => {
      if (isSubscribed) fn();
      else router.push("/paywall");
    },
    [isSubscribed, router],
  );
}
