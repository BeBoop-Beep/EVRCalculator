/**
 * Centralized rank tier configuration.
 * Used by RankBadge and any other rank-display components across the app.
 *
 * Tier assignment (based on topPercent within a scored set):
 *   S  → top 10%
 *   A  → top 11–25%
 *   B  → top 26–50%
 *   C  → top 51–75%
 *   D  → bottom 26–100% (not top 75%)
 *   F  → reserved for explicit "fail" states (not auto-assigned from rank)
 */
/**
 * Colors are raw CSS values (not Tailwind class names) to avoid build-time
 * purging of dynamically-constructed class strings.
 *
 * Each tier has:
 *   color       — text / border color (used via inline styles)
 *   glowColor   — box-shadow glow rgba string (null = no glow)
 *   gradient    — if true, RankBadge renders S-tier gradient text
 */
export const RANK_CONFIG = {
  S: {
    label: "S",
    // Gradient text: purple → pink → amber
    gradientText: "linear-gradient(135deg, #c084fc 0%, #f472b6 50%, #fbbf24 100%)",
    color: "rgba(192,132,252,0.95)",        // purple-400 for border
    glowColor: "rgba(168,85,247,0.45)",
    gradient: true,
    glow: true,
  },
  A: {
    label: "A",
    color: "rgba(52,211,153,0.9)",           // emerald-400
    glowColor: null,
    gradient: false,
    glow: false,
  },
  B: {
    label: "B",
    color: "rgba(134,239,172,0.85)",         // green-300
    glowColor: null,
    gradient: false,
    glow: false,
  },
  C: {
    label: "C",
    color: "rgba(253,224,71,0.9)",           // yellow-300
    glowColor: null,
    gradient: false,
    glow: false,
  },
  D: {
    label: "D",
    color: "rgba(251,146,60,0.9)",           // orange-400
    glowColor: null,
    gradient: false,
    glow: false,
  },
  F: {
    label: "F",
    color: "rgba(248,113,113,0.9)",          // red-400
    glowColor: null,
    gradient: false,
    glow: false,
  },
};

/**
 * Map a topPercent value (0–100, lower = better rank) to a tier letter.
 * Returns null when context is unavailable.
 *
 * @param {number|null} topPercent
 * @returns {"S"|"A"|"B"|"C"|"D"|null}
 */
export function topPercentToTier(topPercent) {
  if (topPercent === null || topPercent === undefined) return null;
  if (topPercent <= 10) return "S";
  if (topPercent <= 25) return "A";
  if (topPercent <= 50) return "B";
  if (topPercent <= 75) return "C";
  return "D";
}
