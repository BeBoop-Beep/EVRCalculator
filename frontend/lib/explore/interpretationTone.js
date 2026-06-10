import { RANK_CONFIG } from "@/constants/rankConfig";

function withAlpha(color, alpha) {
  if (typeof color !== "string") {
    return color;
  }

  const rgbaMatch = color.match(/^rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*[^)]+)?\)$/i);
  if (!rgbaMatch) {
    return color;
  }

  return `rgba(${rgbaMatch[1]},${rgbaMatch[2]},${rgbaMatch[3]},${alpha})`;
}

function normalizeTier(value) {
  const normalized = String(value || "").trim().toUpperCase();
  if (["S", "A", "B", "C", "D", "F"].includes(normalized)) {
    return normalized;
  }
  return null;
}

const TIER_TO_TONE_KEY = {
  S: "elite",
  A: "strong",
  B: "solid",
  C: "neutral",
  D: "caution",
  F: "danger",
};

const TONE_PALETTE = {
  elite: {
    accentColor: "rgba(192,132,252,0.96)",
    borderColor: "rgba(192,132,252,0.22)",
    textColor: "rgba(192,132,252,0.86)",
    softBackground: "rgba(39,18,57,0.52)",
    badgeBackground: "rgba(2,8,23,0.58)",
  },
  strong: {
    accentColor: "rgba(45,212,191,0.96)",
    borderColor: "rgba(45,212,191,0.22)",
    textColor: "rgba(45,212,191,0.86)",
    softBackground: "rgba(10,37,37,0.52)",
    badgeBackground: "rgba(2,8,23,0.58)",
  },
  solid: {
    accentColor: "rgba(134,239,172,0.96)",
    borderColor: "rgba(134,239,172,0.22)",
    textColor: "rgba(134,239,172,0.86)",
    softBackground: "rgba(14,42,26,0.52)",
    badgeBackground: "rgba(2,8,23,0.58)",
  },
  caution: {
    accentColor: "rgba(251,146,60,0.96)",
    borderColor: "rgba(251,146,60,0.22)",
    textColor: "rgba(251,146,60,0.86)",
    softBackground: "rgba(58,30,10,0.52)",
    badgeBackground: "rgba(2,8,23,0.58)",
  },
  danger: {
    accentColor: "rgba(251,113,133,0.96)",
    borderColor: "rgba(251,113,133,0.22)",
    textColor: "rgba(251,113,133,0.86)",
    softBackground: "rgba(58,19,28,0.52)",
    badgeBackground: "rgba(2,8,23,0.58)",
  },
  neutral: {
    accentColor: "rgba(125,211,252,0.96)",
    borderColor: "rgba(125,211,252,0.22)",
    textColor: "rgba(125,211,252,0.86)",
    softBackground: "rgba(22,36,55,0.5)",
    badgeBackground: "rgba(2,8,23,0.58)",
  },
};

function getRankTonePalette(tier, fallbackPalette) {
  const rankColor = RANK_CONFIG[tier]?.color;
  if (!rankColor) {
    return fallbackPalette;
  }

  return {
    accentColor: withAlpha(rankColor, 0.96),
    borderColor: withAlpha(rankColor, 0.22),
    textColor: withAlpha(rankColor, 0.86),
    softBackground: withAlpha(rankColor, 0.14),
    badgeBackground: "rgba(2,8,23,0.58)",
  };
}

function resolveToneKey({ label, rankTier, severity }) {
  const normalizedTier = normalizeTier(rankTier);
  if (normalizedTier) {
    return TIER_TO_TONE_KEY[normalizedTier] || "neutral";
  }

  const normalizedLabel = String(label || "").toLowerCase();

  if (normalizedLabel.includes("elite") || normalizedLabel.includes("best")) {
    return "elite";
  }

  if (
    normalizedLabel.includes("strong") ||
    normalizedLabel.includes("good")
  ) {
    return "strong";
  }

  if (normalizedLabel.includes("solid") || normalizedLabel.includes("balanced")) {
    return "solid";
  }

  if (normalizedLabel.includes("mixed") || normalizedLabel.includes("caution")) {
    return "caution";
  }

  if (
    normalizedLabel.includes("weak") ||
    normalizedLabel.includes("poor") ||
    normalizedLabel.includes("risky")
  ) {
    return "danger";
  }

  if (severity === "positive") {
    return "strong";
  }

  if (severity === "caution") {
    return "caution";
  }

  if (severity === "negative") {
    return "danger";
  }

  return "neutral";
}

export function getTierTone(rankTier) {
  const tier = normalizeTier(rankTier);
  if (!tier) {
    return null;
  }

  const toneKey = TIER_TO_TONE_KEY[tier] || "neutral";
  const basePalette = TONE_PALETTE[toneKey] || TONE_PALETTE.neutral;
  const palette = getRankTonePalette(tier, basePalette);
  const tierConfig = RANK_CONFIG[tier] || null;

  return {
    tier,
    toneKey,
    rankColor: tierConfig?.color || palette.accentColor,
    accentColor: palette.accentColor,
    borderColor: palette.borderColor,
    textColor: palette.textColor,
    softBackground: palette.softBackground,
    badgeBackground: palette.badgeBackground,
  };
}

export function getInterpretationTone({ label, rankTier, severity } = {}) {
  const toneKey = resolveToneKey({ label, rankTier, severity });
  const palette = TONE_PALETTE[toneKey] || TONE_PALETTE.neutral;
  const tierTone = getTierTone(rankTier);
  const accentColor = tierTone?.accentColor || palette.accentColor;
  const borderColor = tierTone?.borderColor || palette.borderColor;
  const textColor = tierTone?.textColor || palette.textColor;
  const softBackground = tierTone?.softBackground || palette.softBackground;
  const badgeBackground = tierTone?.badgeBackground || palette.badgeBackground;

  return {
    toneKey: tierTone?.toneKey || toneKey,
    accentColor,
    borderColor,
    textColor,
    softBackground,
    badgeBackground,
    badgeBorderColor: borderColor,
    badgeTextColor: textColor,
    dotColor: accentColor,
    glowColor: withAlpha(accentColor, 0.18),
    panelShadow: `0 0 18px ${withAlpha(accentColor, 0.14)}`,
  };
}

export function getInterpretationBadgeStyle({ label, rankTier, severity } = {}) {
  const tone = getInterpretationTone({ label, rankTier, severity });
  return {
    background: tone.badgeBackground,
    borderColor: tone.badgeBorderColor,
    color: tone.badgeTextColor,
    boxShadow: `0 0 5px 0px ${tone.glowColor}, inset 0 0 4px ${withAlpha(tone.accentColor, 0.03)}`,
  };
}

export function getCalloutAccentStyle({ label, rankTier, severity } = {}) {
  const tone = getInterpretationTone({ label, rankTier, severity });
  return {
    borderLeftColor: tone.accentColor,
    backgroundColor: tone.softBackground,
    boxShadow: tone.panelShadow,
    dotColor: tone.dotColor,
  };
}

export function getDangerValueStyle() {
  const dangerColor = RANK_CONFIG.F?.color || "rgba(248,113,113,0.9)";
  return {
    color: dangerColor,
    textShadow: `0 0 10px ${withAlpha(dangerColor, 0.28)}`,
  };
}
