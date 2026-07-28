// One semantic presentation source for every surface that renders a RIP tier.
//
// The tier -> colour mapping itself is NOT duplicated here. RANK_CONFIG stays
// the single source of tier colours and interpretationTone.js resolves a tier
// (or, when no tier is present, an interpretation label/severity) to one accent
// colour. This module turns that ONE resolved accent into the concrete
// treatments the RIP surfaces share:
//
//   * the Opening Outlook accent rail and its horizontal wash, and
//   * the title-card tier / rank / verdict pills,
//
// so the title card and the detailed RIP Score Breakdown cannot drift apart and
// no surface can hard-code a single tier's colour (the B-tier green).
//
// It is dependency-free on purpose: ripTierPresentation.test.mjs runs it
// directly under `node --test` / `tsx --test`, which cannot resolve the "@/"
// specifiers the Next bundler uses.

// Slate-400 — the neutral used when neither a tier nor a label resolves, so a
// set with no tier still renders a coherent (colourless) treatment.
export const RIP_TIER_NEUTRAL_RGB = "148,163,184";

/**
 * "rgba(134,239,172,0.85)" -> "134,239,172". Returns null for anything that is
 * not an rgb()/rgba() string so callers fall back to the neutral triplet.
 */
export function toRgbTriplet(color) {
  if (typeof color !== "string") {
    return null;
  }
  const match = color.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*[^)]+)?\)$/i);
  if (!match) {
    return null;
  }
  return `${match[1]},${match[2]},${match[3]}`;
}

// The Opening Outlook wash. Strongest beside the rail, already faint behind the
// start of the sentence, and fully transparent well before the right edge — so
// the treatment reads as an accent on the section rather than as a filled alert
// banner. The last stop is rgba(r,g,b,0) rather than the `transparent` keyword
// so no engine interpolates through black on the way out.
export const RIP_OUTLOOK_WASH_STOPS = [
  { offset: "0%", alpha: 0.115 },
  { offset: "30%", alpha: 0.055 },
  { offset: "56%", alpha: 0.02 },
  { offset: "82%", alpha: 0 },
];

/**
 * @param {{ tier?: string|null, accentColor?: string|null }} input
 *   `accentColor` is the already-resolved semantic accent (see
 *   `getRipTierPresentation` in interpretationTone.js). `tier` is carried
 *   through for callers that want to key render logic or tests on it.
 */
export function buildRipTierPresentation({ tier = null, accentColor = null } = {}) {
  const rgb = toRgbTriplet(accentColor) || RIP_TIER_NEUTRAL_RGB;
  const tint = (alpha) => `rgba(${rgb},${alpha})`;

  return {
    tier: tier || null,
    rgb,
    accentColor: tint(0.96),

    // Opening Outlook. The rail is a 2px border-left drawn by the markup; the
    // glow is offset to the left and given a negative spread so it is clipped
    // to a narrow halo hugging that rail. An outer box-shadow never paints
    // inside its own border box, so this cannot produce a right-hand edge.
    outlookRail: {
      borderLeftColor: tint(0.9),
      boxShadow: `-4px 0 16px -8px ${tint(0.55)}`,
    },
    outlookWash: `linear-gradient(90deg, ${RIP_OUTLOOK_WASH_STOPS.map(
      (stop) => `${tint(stop.alpha)} ${stop.offset}`
    ).join(", ")})`,

    // Title-card metadata. Deliberately unequal: the tier carries the strongest
    // border/text, the verdict relates to it at lower weight, and the rank is
    // the quietest of the three (same colour family, near-neutral text).
    tierPill: {
      borderColor: tint(0.46),
      color: tint(0.96),
      backgroundColor: tint(0.1),
    },
    rankPill: {
      borderColor: tint(0.2),
      color: "rgba(226,232,240,0.78)",
      backgroundColor: tint(0.045),
    },
    verdictPill: {
      borderColor: tint(0.24),
      color: tint(0.82),
      backgroundColor: tint(0.055),
    },
  };
}
