// View-models for the homepage product previews.
//
// READ-ONLY AND DERIVED FROM ALREADY-FETCHED DATA. Every function here takes
// the landing entries built by landingHeroSpotlight.mjs — which come out of the
// SAME single RIP Statistics targets payload the hero already requests — and
// reshapes them for a preview component. Nothing in this file fetches, scores,
// ranks against a cohort, or fills a missing number in: a signal the payload
// does not carry comes back null and the preview drops that row rather than
// publishing a placeholder on a marketing page.
//
// Dependency-free so landingPreviews.test.mjs can run it under `tsx --test`,
// which cannot resolve the "@/" specifiers the Next bundler uses.

function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toList(value) {
  return Array.isArray(value) ? value : [];
}

function toLimit(value, fallback) {
  return Number.isFinite(value) && value > 0 ? Math.floor(value) : fallback;
}

/**
 * The 7-day set value movement, or null when there is nothing truthful to
 * show. `status !== "available"` is the backend saying there is no comparable
 * snapshot (a new set, or a gap in history) — that is NOT a zero, and it is
 * deliberately not rendered as one.
 */
export function selectSetValueMovement(entry) {
  const current = toFiniteNumber(entry?.setValue);
  const previous = toFiniteNumber(entry?.previousSetValue7d);
  if (entry?.setValueStatus7d !== "available") return null;
  if (current === null || previous === null || previous <= 0) return null;

  const amount = current - previous;
  return {
    amount,
    percent: (amount / previous) * 100,
    direction: amount > 0 ? "up" : amount < 0 ? "down" : "flat",
  };
}

/**
 * Opening Profit vs Cost, as the Overview module frames it: what one pack
 * costs against the modeled mean value an opening returns, plus the published
 * probability an opening lands above cost.
 *
 * `share` is the cost's width as a fraction of the larger of the two bars —
 * a presentational ratio for drawing them to scale, not a score. Both source
 * numbers are required; a set missing either has no comparison to draw.
 */
export function selectOpeningEconomics(entry) {
  const packCost = toFiniteNumber(entry?.packCost);
  const meanValue = toFiniteNumber(entry?.meanValue);
  if (packCost === null || meanValue === null || packCost <= 0 || meanValue < 0) {
    return null;
  }

  const ceiling = Math.max(packCost, meanValue);
  return {
    packCost,
    meanValue,
    probProfit: toFiniteNumber(entry?.probProfit),
    costShare: ceiling > 0 ? packCost / ceiling : 0,
    valueShare: ceiling > 0 ? meanValue / ceiling : 0,
    // Which side of cost the modeled mean lands on. The magnitude is never
    // published as a headline number — the two bars carry the comparison.
    standing: meanValue > packCost ? "above" : meanValue < packCost ? "below" : "even",
  };
}

/**
 * The compact Explore ranking: the cohort's own RIP rank order, already
 * computed by selectLandingHeroEntries. Rows without a rank are dropped rather
 * than renumbered, so a position shown here is always the backend's rank.
 */
export function selectExploreRankingRows(entries, limit = 5) {
  return toList(entries)
    .filter((entry) => toFiniteNumber(entry?.rank) !== null)
    .slice(0, toLimit(limit, 5))
    .map((entry) => ({
      key: entry.key,
      name: entry.name,
      era: entry.era,
      logoUrl: entry.logoUrl || entry.symbolUrl || null,
      rank: toFiniteNumber(entry.rank),
      score: toFiniteNumber(entry.score),
      scoreLabel: entry.scoreLabel,
      tier: entry.tier || null,
      setValue: toFiniteNumber(entry.setValue),
      movement: selectSetValueMovement(entry),
      href: entry.overviewHref || entry.href,
    }));
}

/**
 * "Best Sets to Rip" reads the same ranked order as the Explore table's default
 * mode. Separated from selectExploreRankingRows so the two ladders on the page
 * can diverge in length without one silently resizing the other.
 */
export function selectBestSetsToRip(entries, limit = 3) {
  return selectExploreRankingRows(entries, limit);
}

/**
 * The set-value ladder, mirroring Explore's Top Rankings: ordered by checklist
 * set value, highest first. The position is this list's own descending order —
 * a presentational index, never a cohort rank — which is how the accessible
 * label describes it.
 */
export function selectSetValueLeaders(entries, limit = 5) {
  return toList(entries)
    .map((entry) => ({ entry, value: toFiniteNumber(entry?.setValue) }))
    .filter((row) => row.value !== null)
    .sort((left, right) => right.value - left.value || left.entry.name.localeCompare(right.entry.name))
    .slice(0, toLimit(limit, 5))
    .map((row, index) => ({
      key: row.entry.key,
      position: index + 1,
      name: row.entry.name,
      logoUrl: row.entry.logoUrl || row.entry.symbolUrl || null,
      setValue: row.value,
      movement: selectSetValueMovement(row.entry),
      href: row.entry.overviewHref || row.entry.href,
    }));
}

/* --------------------------------------------------- pokemon product content --- */

/**
 * The chase cards a set is known for: real card art, real names, real prices,
 * real 7-day movement. A card without an image is dropped — the point of this
 * row is category recognition, and a nameplate with no art does not carry it.
 *
 * Reads the SAME `/market/top-chase` contract the set Overview reads, through
 * the same aliases (`imageSmallUrl` / `image_url`, `marketPrice` /
 * `currentPrice`), so a card shown here is the card Overview shows.
 */
export function selectChaseCards(payload, limit = 3) {
  const cards = Array.isArray(payload?.topChaseCards)
    ? payload.topChaseCards
    : Array.isArray(payload?.top_chase_cards)
      ? payload.top_chase_cards
      : [];

  return cards
    .map((card) => {
      const image =
        String(card?.imageSmallUrl || card?.imageUrl || card?.image_url || "").trim() || null;
      const name = String(card?.name || "").trim();
      if (!image || !name) return null;

      const seven = card?.marketDeltaWindows?.["7D"] ?? card?.market_delta_windows?.["7D"] ?? null;
      const changePercent = toFiniteNumber(seven?.changePercent ?? seven?.change_percent);

      return {
        key: String(card?.canonicalCardId || card?.cardId || card?.id || name),
        name,
        image,
        rarity: String(card?.rarity || "").trim() || null,
        number: String(card?.setNumber || card?.set_number || "").trim() || null,
        price: toFiniteNumber(card?.marketPrice ?? card?.currentPrice ?? card?.estimatedMarketPrice),
        changePercent,
        direction:
          changePercent === null ? null : changePercent > 0 ? "up" : changePercent < 0 ? "down" : "flat",
      };
    })
    .filter(Boolean)
    .slice(0, toLimit(limit, 3));
}

/**
 * Display labels for the sealed families the /market/sealed contract publishes.
 * Derived from the machine key rather than the payload's own label string,
 * which round-trips a non-ASCII "Pokémon" through several layers.
 */
const SEALED_FAMILY_LABELS = Object.freeze({
  booster_box: "Booster Box",
  booster_bundle: "Booster Bundle",
  booster_pack: "Booster Pack",
  sleeved_booster_pack: "Sleeved Booster Pack",
  elite_trainer_box: "Elite Trainer Box",
  pokemon_center_elite_trainer_box: "Pokémon Center ETB",
});

/** Most recognizable first — a box says "sealed Pokémon" faster than a pack. */
const SEALED_FAMILY_ORDER = [
  "booster_box",
  "elite_trainer_box",
  "pokemon_center_elite_trainer_box",
  "booster_bundle",
  "booster_pack",
  "sleeved_booster_pack",
];

/**
 * The real sealed products a set is sold as, one per family, priced.
 *
 * NOTE: the sealed contract publishes names, families and prices but NO image
 * field, and no sealed artwork exists locally either — so these render as typed
 * product lines, never as an invented box render.
 */
export function selectSealedProducts(payload, limit = 2) {
  const products = Array.isArray(payload?.products) ? payload.products : [];
  const byFamily = new Map();

  for (const product of products) {
    const family = String(product?.productFamily || product?.product_family || "").trim();
    const price = toFiniteNumber(product?.currentPrice ?? product?.current_price);
    if (!family || price === null) continue;
    const existing = byFamily.get(family);
    if (!existing || price > existing.price) {
      byFamily.set(family, {
        key: String(product?.sealedProductId || product?.sealed_product_id || family),
        family,
        label: SEALED_FAMILY_LABELS[family] || null,
        name: String(product?.name || "").trim() || null,
        price,
        priceAsOf: String(product?.priceAsOf || product?.price_as_of || "").trim() || null,
      });
    }
  }

  return SEALED_FAMILY_ORDER.map((family) => byFamily.get(family))
    .filter((entry) => entry && entry.label)
    .slice(0, toLimit(limit, 2));
}

/**
 * The live market strip: up to three published signals, each one a different
 * question. Any signal whose data is missing is omitted rather than filled in.
 *
 * `mover` comes from the SAME global 7-day card movers payload the Explore
 * ticker reads, so the card named here is the card Explore names.
 */
export function selectMarketSignals({ entries = [], openingSpotlightSet = null, moversPayload = null } = {}) {
  const list = toList(entries);
  const signals = [];

  // The SAME set the hero features — passed in rather than re-derived, so the
  // strip and the hero can never disagree about who is ranked first.
  const topOpening = openingSpotlightSet;
  if (topOpening && toFiniteNumber(topOpening.rank) !== null) {
    signals.push({
      key: "opening",
      label: "Best opening profile",
      setName: topOpening.name,
      logoUrl: topOpening.logoUrl || topOpening.symbolUrl || null,
      // The rank leads here too; the score is not a percentage and must not
      // read as one on a strip this compact.
      value: `#${topOpening.rank}`,
      unit: "Opening rank",
      tier: topOpening.tier || null,
      href: topOpening.overviewHref || topOpening.href,
    });
  }

  const topValue = selectSetValueLeaders(list, 1)[0] || null;
  if (topValue) {
    signals.push({
      key: "value",
      label: "Highest tracked set value",
      setName: topValue.name,
      logoUrl: topValue.logoUrl,
      value: topValue.setValue,
      unit: "Set value",
      movement: topValue.movement,
      href: topValue.href,
    });
  }

  const movers = Array.isArray(moversPayload?.marketMovers?.all) ? moversPayload.marketMovers.all : [];
  const mover = movers
    .map((card) => {
      const percent = toFiniteNumber(card?.change7dPercent ?? card?.change_7d_percent ?? card?.changePercent);
      const image = String(card?.imageSmallUrl || card?.imageUrl || card?.image_url || "").trim() || null;
      const name = String(card?.name || "").trim();
      if (percent === null || !name) return null;
      return {
        name,
        image,
        setName: String(card?.setName || "").trim() || null,
        price: toFiniteNumber(card?.currentPrice ?? card?.marketPrice),
        percent,
      };
    })
    .filter(Boolean)
    .sort((left, right) => Math.abs(right.percent) - Math.abs(left.percent))[0];

  if (mover) {
    signals.push({
      key: "mover",
      label: "Largest 7D card move",
      setName: mover.setName,
      cardName: mover.name,
      cardImage: mover.image,
      value: mover.price,
      unit: "Card price",
      movement: {
        percent: mover.percent,
        amount: null,
        direction: mover.percent > 0 ? "up" : mover.percent < 0 ? "down" : "flat",
      },
      href: "/Explore",
    });
  }

  return signals;
}

/**
 * The facts the methodology section is allowed to state as numbers. Anything
 * the payload does not carry stays null and the section omits that line — no
 * hardcoded set counts, no invented update cadence, no simulation scale we
 * cannot read.
 */
export function selectMarketContext({ entries = [], meta = null } = {}) {
  const list = toList(entries);
  const marketDate =
    meta?.comparisonSnapshots?.currentMarketDate ??
    meta?.comparisonSnapshots?.current_market_date ??
    null;

  return {
    trackedSetCount: list.length > 0 ? list.length : null,
    rankedSetCount: list.filter((entry) => toFiniteNumber(entry?.rank) !== null).length || null,
    marketDate: typeof marketDate === "string" && marketDate.trim() ? marketDate.trim() : null,
  };
}
