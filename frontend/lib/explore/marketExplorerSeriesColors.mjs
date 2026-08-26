// ---------------------------------------------------------------------------
// Market Explorer — the ONE series-color registry.
//
// A market's color is its IDENTITY. The same market must be the same color in
// the rail, the legend, the Active Markets chips, the chart and the detail
// table, every time it appears, in every session. Before this module each of
// those surfaces read a color from whichever model happened to build it, and
// the prepared palettes had drifted into hue families: Raw / SIR / IR / Ultra
// Rare all sat in the violet band and the five sealed families all sat in the
// orange-amber band, so selecting four related markets produced four lines a
// reader could not tell apart.
//
// TWO RULES GOVERN EVERY VALUE BELOW.
//
//   1. IDENTITY IS NOT STATE. Green is the interaction color — selected rows,
//      focus rings, primary actions — and never a series identity. A selected
//      SIR row is a GREEN row carrying a VIOLET marker.
//
//   2. IDENTITY IS NOT PERFORMANCE. The bright gain-green and loss-red are
//      return semantics and are reserved. RESERVED_HUE_RANGES keeps generated
//      colors out of those bands so a custom market can never be handed a hue
//      that reads as "this line is up".
//
// Colors are assigned by KEY, never by selection order, so adding or removing a
// market cannot repaint the lines around it.
// ---------------------------------------------------------------------------

/**
 * Explicit identity per canonical prepared series.
 *
 * Hues are spread deliberately rather than grouped by asset: the readability
 * problem this registry exists to solve is exactly the case where a parent and
 * its own children are charted together, so a child must NOT inherit its
 * parent's hue family.
 */
export const MARKET_EXPLORER_SERIES_COLORS = Object.freeze({
  // Written as HSL because the constraint this table has to satisfy is a HUE
  // constraint: every value must sit outside the reserved gain/loss/interaction
  // bands and far enough from its neighbours to be told apart on a dark chart.
  // Hex or rgb() would hide exactly the property that matters here.
  //
  // The two asset groups occupy different halves of the wheel — sealed warm,
  // cards cool — so a reader can tell WHICH KIND of market a line is at a
  // glance, while inside each group the members are spread ~10-25 degrees apart
  // instead of clustered. Lightness varies slightly as a second cue.

  // --- Asset classes ---
  raw: "hsl(258 72% 70%)",              // violet
  sealedMarket: "hsl(43 92% 57%)",      // amber
  // Graded is a placeholder that is never drawn — the Market Overview row and
  // the Explorer rail option both report it unavailable. Deliberately
  // desaturated so it cannot be mistaken for a live series in a swatch.
  // Registered under BOTH ids it is known by: the Market Overview placeholder
  // calls it `graded`, the Explorer rail option `gradedMarket`.
  graded: "hsl(213 16% 65%)",
  gradedMarket: "hsl(213 16% 65%)",

  // --- Benchmarks ---
  topChase: "hsl(200 85% 60%)",         // sky

  // --- Card rarities of the RAW CARD MARKET (cool half) ---
  //
  // The same rarity over the Top Chase cohort is a DIFFERENT market with its
  // own `card:topChase:` key, and is deliberately not registered: it takes a
  // stable generated color instead, so the two can never be confused for one
  // series wearing one color.
  "card:raw:rareSecret": "hsl(212 70% 55%)",
  "card:raw:illustrationRare": "hsl(222 78% 66%)",
  "card:raw:rareHolo": "hsl(232 62% 72%)",
  "card:raw:hyperRare": "hsl(243 76% 64%)",
  "card:raw:rareUltra": "hsl(272 62% 60%)",
  "card:raw:specialIllustrationRare": "hsl(287 78% 68%)",
  "card:raw:doubleRare": "hsl(303 66% 58%)",
  "card:raw:ultraRare": "hsl(322 76% 62%)",
  "card:raw:rareRainbow": "hsl(338 74% 70%)",

  // --- Sealed product families (warm half, plus one cyan) ---
  "sealed:boosterBox": "hsl(22 88% 55%)",
  "sealed:pokemonCenterEliteTrainerBox": "hsl(33 62% 47%)",   // bronze
  "sealed:eliteTrainerBox": "hsl(66 72% 52%)",                // yellow-lime
  "sealed:boosterBundle": "hsl(88 58% 55%)",                  // olive-green
  // Packs sits in the narrow non-reserved gap below the interaction band. It is
  // the one sealed family outside the warm half, because six distinguishable
  // warm hues do not exist between the loss band and the gain band.
  "sealed:packs": "hsl(185 78% 52%)",
});

/**
 * Hue bands a generated color may never land in.
 *
 * `gain` and `loss` are the return vocabulary. `interaction` is the inDex green
 * used by focus rings, selected rows and primary CTAs — a chart line in that
 * exact green would read as a control.
 */
export const RESERVED_HUE_RANGES = Object.freeze([
  { name: "gain", start: 100, end: 155 },
  { name: "loss", start: 348, end: 372 },   // wraps past 360; see isReservedHue
  { name: "interaction", start: 166, end: 180 },
]);

/** The canonical inDex interaction green. Interaction ONLY — never a series. */
export const INTERACTION_ACCENT = "rgb(45,212,191)";

export function isReservedHue(hue) {
  const normalized = ((Number(hue) % 360) + 360) % 360;
  return RESERVED_HUE_RANGES.some(({ start, end }) => {
    if (end <= 360) return normalized >= start && normalized <= end;
    // A range that wraps past 360 covers [start,360) plus [0,end-360].
    return normalized >= start || normalized <= end - 360;
  });
}

/**
 * The registry color for a canonical series key, or null when it has none.
 *
 * Returning null rather than a fallback is deliberate: the caller decides
 * whether an unregistered key is a bug (a prepared series) or expected (a
 * custom query), and a silent grey would hide the former.
 */
export function seriesColorForKey(key) {
  const identity = MARKET_EXPLORER_SERIES_COLORS[String(key || "")];
  return identity || null;
}

/** The same color at low alpha, for tinted fills under a line. */
export function softSeriesColor(color, alpha = 0.16) {
  const value = String(color || "");
  const rgb = value.match(/^rgb\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)\s*\)$/);
  if (rgb) return `rgba(${rgb[1]},${rgb[2]},${rgb[3]},${alpha})`;
  const hsl = value.match(/^hsl\(\s*([\d.]+)[\s,]+([\d.]+)%[\s,]+([\d.]+)%\s*\)$/);
  if (hsl) return `hsla(${hsl[1]},${hsl[2]}%,${hsl[3]}%,${alpha})`;
  return value;
}

/** FNV-1a. Small, dependency-free, and identical on server and client. */
function fingerprintHash(value) {
  let hash = 2166136261;
  for (const character of String(value || "query")) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

/**
 * How many distinct hues a generated color may take.
 *
 * A prime step walked around the wheel spreads consecutive hash values far
 * apart, so two custom markets built minutes apart are very unlikely to land
 * adjacent. Perfect collision avoidance is impossible without knowing the other
 * active queries; this makes obvious collisions rare, which is what the design
 * asks for.
 */
const GENERATED_HUE_STEP = 47;
const GENERATED_HUE_SLOTS = 360 / 5;

/**
 * A deterministic identity color for a market with no registry entry.
 *
 * DERIVED FROM THE FINGERPRINT, NOT FROM SELECTION ORDER. The same custom query
 * is the same color in every session and after every hydration; adding a second
 * query never repaints the first.
 */
export function colorForSeriesFingerprint(fingerprint) {
  const hash = fingerprintHash(fingerprint);
  for (let attempt = 0; attempt < GENERATED_HUE_SLOTS; attempt += 1) {
    const hue = ((hash + attempt * GENERATED_HUE_STEP) * 5) % 360;
    if (!isReservedHue(hue)) return `hsl(${hue} 70% 62%)`;
  }
  // Unreachable while the reserved ranges leave any slot free; a stable
  // non-reserved fallback is still better than throwing inside a render.
  return "hsl(280 70% 62%)";
}

/**
 * Identity for any series: registry first, fingerprint second.
 *
 * This is the ONLY function a component should call. A rail, a legend and a
 * chart that all call it cannot disagree.
 */
export function resolveSeriesIdentityColor(key, fingerprint = null) {
  return seriesColorForKey(key) || colorForSeriesFingerprint(fingerprint || key);
}
