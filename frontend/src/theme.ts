// Design tokens for PACED. Dark-first theme.
// A plain key is a background, its `on` partner is the text/icon color on top of it.

import { useMemo } from "react";
import { Appearance, StyleSheet, type ImageStyle, type TextStyle, type ViewStyle } from "react-native";

export type ColorScheme = "light" | "dark";

const dark = {
  surface: "#101312",
  onSurface: "#F2F1EC",
  surfaceSecondary: "#171B1A",
  onSurfaceSecondary: "#DCDBD4",
  surfaceTertiary: "#202523",
  onSurfaceTertiary: "#B7BCB7",
  surfaceInverse: "#F2F1EC",
  onSurfaceInverse: "#101312",
  muted: "#858C88",

  brand: "#1B4D36",
  onBrand: "#F2F1EC",
  brandPrimary: "#1F5A3F",
  onBrandPrimary: "#F2F1EC",
  brandSecondary: "#AEB4B6",
  onBrandSecondary: "#101312",
  brandTertiary: "rgba(143, 201, 163, 0.10)",
  onBrandTertiary: "#8FC9A3",

  accent: "#8FC9A3",
  accentLine: "#3E7D5E",
  silver: "#AEB4B6",

  success: "#6FBF8E",
  onSuccess: "#101312",
  warning: "#D4A955",
  onWarning: "#101312",
  error: "#D9645C",
  onError: "#F2F1EC",
  info: "#A9BCCB",
  onInfo: "#101312",

  border: "#262C2A",
  borderStrong: "#36403C",
  divider: "#222826",

  scrim: "rgba(16, 19, 18, 0.93)",
  scrimLight: "rgba(16, 19, 18, 0.15)",
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

type NamedStyles<T> = { [K in keyof T]: ViewStyle | TextStyle | ImageStyle };

export function makeStyles<T extends NamedStyles<T>>(
  factory: (colors: ThemeColors) => T,
): () => T {
  return function useStyles(): T {
    const { colors: c } = useTheme();
    return useMemo(() => StyleSheet.create(factory(c) as any) as T, [c]);
  };
}
