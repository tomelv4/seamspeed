// Design tokens for PaceSensei. Dark-first theme (from /app/design_guidelines.json).
// A plain key is a background, its `on` partner is the text/icon color on top of it.

import { useMemo } from "react";
import { Appearance, StyleSheet } from "react-native";

export type ColorScheme = "light" | "dark";

const dark = {
  surface: "#0F1115",
  onSurface: "#FFFFFF",
  surfaceSecondary: "#1A1D24",
  onSurfaceSecondary: "#E2E8F0",
  surfaceTertiary: "#252933",
  onSurfaceTertiary: "#CBD5E1",
  surfaceInverse: "#FFFFFF",
  onSurfaceInverse: "#0F1115",
  muted: "#94A3B8",

  brand: "#FF5A25",
  onBrand: "#FFFFFF",
  brandPrimary: "#FF5A25",
  onBrandPrimary: "#FFFFFF",
  brandSecondary: "#FF7E54",
  onBrandSecondary: "#000000",
  brandTertiary: "rgba(255, 90, 37, 0.15)",
  onBrandTertiary: "#FF5A25",

  success: "#10B981",
  onSuccess: "#FFFFFF",
  warning: "#F59E0B",
  onWarning: "#FFFFFF",
  error: "#EF4444",
  onError: "#FFFFFF",
  info: "#3B82F6",
  onInfo: "#FFFFFF",

  border: "#2D3340",
  borderStrong: "#3F4759",
  divider: "#2D3340",

  scrim: "rgba(15, 17, 21, 0.92)",
  scrimLight: "rgba(15, 17, 21, 0.1)",
};

export type ThemeColors = typeof dark;

export const defaultScheme = "dark" satisfies ColorScheme;

export const themes: { light?: ThemeColors; dark: ThemeColors } = { dark };

export const colors = dark;

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}

setColorScheme?.(defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  return { scheme: "dark", colors: dark };
}

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors: c } = useTheme();
    return useMemo(() => StyleSheet.create(factory(c)), [c]);
  };
}
