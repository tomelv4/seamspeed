export const fonts = {
  display: "Sora-SemiBold",
  displaySemi: "Sora-Medium",
  mono: "JetBrainsMono-Medium",
  text: "Manrope-Medium",
  textBold: "Manrope-Bold",
  textXBold: "Manrope-ExtraBold",
};

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32, xxxl: 48 };
export const radius = { sm: 4, md: 8, lg: 16, pill: 999 };

export const PHASES = [
  { key: "run_up", label: "Run-up" },
  { key: "load", label: "Load" },
  { key: "back_foot", label: "Back Foot" },
  { key: "front_foot", label: "Front Foot" },
  { key: "release", label: "Release" },
  { key: "follow_through", label: "Follow-through" },
];

export const phaseLabel = (key?: string) => PHASES.find((p) => p.key === key)?.label ?? key ?? "";

export const IMAGES = {
  hero: "https://images.pexels.com/photos/12732253/pexels-photo-12732253.jpeg?auto=compress&w=900",
  analyze: "https://images.pexels.com/photos/34497242/pexels-photo-34497242.jpeg?auto=compress&w=900",
  drills: [
    "https://images.pexels.com/photos/39423291/pexels-photo-39423291.jpeg?auto=compress&w=800",
    "https://images.pexels.com/photos/13204961/pexels-photo-13204961.jpeg?auto=compress&w=800",
    "https://images.pexels.com/photos/34497242/pexels-photo-34497242.jpeg?auto=compress&w=800",
  ],
};
