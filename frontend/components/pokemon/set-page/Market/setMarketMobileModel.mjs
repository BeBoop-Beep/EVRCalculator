// ---------------------------------------------------------------------------
// Presentation model for the MOBILE Set Market tab.
//
// Every function here is pure and derives ONLY from data the page already
// publishes. Nothing invents a metric: when a value is absent the model returns
// null and the components omit the cell rather than printing a placeholder
// number. That rule is what keeps this surface honest for sets whose snapshots
// are thin (a brand-new set has movers but no 1Y set-value history, and a set
// with a single sealed product has no product row to switch between).
//
// It deliberately mirrors — rather than imports — the desktop page's private
// price ladder. RipStatisticsPageClient.jsx is a 14k-line client component that
// already imports this directory, so reaching back into it for
// `getCardMarketPrice` would be a cycle. The same duplication already exists in
// Insights/cardDemandValidationSelector.mjs for the same reason, and the ladder
// is covered by this module's own tests.
// ---------------------------------------------------------------------------

import { getHistoryDateKey } from "../../../explore/historyDateFormatting.mjs";
import { forwardFillDailyHistoryThroughDate } from "../../../explore/packValueHistoryNormalization.mjs";
import {
  getTopCardPreferredHistoryEndDate,
  resolveTopCardWindowState,
} from "../../../explore/topChaseWindowState.mjs";
import { selectMoversTickerItems } from "../../../explore/moversTickerSelector.mjs";
import {
  compactSealedProductLabel,
  selectSealedWindow,
  sortSealedProductsByCurrentPrice,
} from "../Overview/sealedMarketTrendSelector.mjs";

export const MOBILE_MOVERS_MAX_ITEMS = 8;
export const MOBILE_TOP_CHASE_PREVIEW_LIMIT = 3;
export const MOBILE_TOP_CHASE_MAX_ROWS = 10;

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const compactCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

export function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Currency for a figure that must stay exact (prices, deltas). */
export function formatMoney(value) {
  const parsed = toFiniteNumber(value);
  return parsed === null ? null : currency.format(parsed);
}

/** Currency for a headline figure where cents are noise (set value, > $1k). */
export function formatCompactMoney(value) {
  const parsed = toFiniteNumber(value);
  if (parsed === null) return null;
  return Math.abs(parsed) >= 1000 ? compactCurrency.format(parsed) : currency.format(parsed);
}

export function formatSignedPercent(value) {
  const parsed = toFiniteNumber(value);
  if (parsed === null) return null;
  return `${parsed >= 0 ? "+" : "−"}${Math.abs(parsed).toFixed(1)}%`;
}

/** Signed currency for a period-change micro-stat: "+$21.86" / "-$886.98" / "-$40k". */
export function formatSignedCompactMoney(value) {
  const parsed = toFiniteNumber(value);
  if (parsed === null) return null;
  const formatted = formatCompactMoney(Math.abs(parsed));
  return formatted === null ? null : `${parsed >= 0 ? "+" : "−"}${formatted}`;
}

export function formatCount(value) {
  const parsed = toFiniteNumber(value);
  return parsed === null || parsed <= 0 ? null : Math.round(parsed).toLocaleString("en-US");
}

export function directionOf(amount, percent = null) {
  const primary = toFiniteNumber(amount) ?? toFiniteNumber(percent);
  if (primary === null) return "neutral";
  return primary > 0 ? "positive" : primary < 0 ? "negative" : "neutral";
}

export function getCardInitials(value) {
  const text = String(value || "").trim();
  if (!text) return "?";
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0] || ""}${words[1][0] || ""}`.toUpperCase();
}

/**
 * The market price a card row prints. Mirrors the desktop ladder; a zero or a
 * negative is treated as "no price", because both mean "not priced yet" in the
 * snapshot rather than "worth nothing".
 */
export function readCardMarketPrice(card) {
  const price =
    toFiniteNumber(card?.marketPrice) ??
    toFiniteNumber(card?.market_price) ??
    toFiniteNumber(card?.currentPrice) ??
    toFiniteNumber(card?.current_price) ??
    toFiniteNumber(card?.price) ??
    toFiniteNumber(card?.estimatedMarketPrice) ??
    toFiniteNumber(card?.estimated_market_price) ??
    toFiniteNumber(card?.currentNearMintPrice) ??
    toFiniteNumber(card?.current_near_mint_price);
  return price !== null && price > 0 ? price : null;
}

export function readCardImageUrl(card) {
  const raw = card?.imageSmallUrl || card?.imageLargeUrl || card?.imageUrl || card?.image_small_url || card?.image_url;
  const text = String(raw || "").trim();
  return text || null;
}

// --- 7D Market Movers -------------------------------------------------------

/**
 * The carousel's cards. Fixed 7D, exactly the rows the shared ticker selector
 * already qualifies — this only reshapes them for a larger touch target and
 * never re-ranks or re-filters.
 */
export function buildMoverCards(entry, { maxItems = MOBILE_MOVERS_MAX_ITEMS } = {}) {
  return selectMoversTickerItems(entry, { maxItems }).map(({ card, movement }, index) => {
    const price = readCardMarketPrice(card);
    const amount = toFiniteNumber(movement?.amount);
    const percent = toFiniteNumber(movement?.percent);
    return {
      key: String(card?.canonicalCardId || card?.cardId || card?.id || card?.name || index),
      name: String(card?.name || "Unknown card"),
      imageUrl: readCardImageUrl(card),
      initials: getCardInitials(card?.name),
      price,
      priceText: formatMoney(price),
      amount,
      amountText: amount === null ? null : `${amount >= 0 ? "+" : "−"}${currency.format(Math.abs(amount))}`,
      percent,
      percentText: formatSignedPercent(percent),
      direction: directionOf(amount, percent),
    };
  });
}

// --- Top Chase Cards --------------------------------------------------------

/**
 * The desktop chase detail wants the LARGEST published artwork, not the
 * thumbnail the compact rows use. Upscaling a small image to fill a detail
 * panel is visible as blur, so the large URL is preferred and the small one is
 * only a fallback for cards that publish nothing else.
 */
export function readCardHeroImageUrl(card) {
  const raw =
    card?.imageLargeUrl ||
    card?.image_large_url ||
    card?.imageUrl ||
    card?.image_url ||
    card?.imageSmallUrl ||
    card?.image_small_url;
  const text = String(raw || "").trim();
  return text || null;
}

export function buildTopChaseHistory(card, selectedWindowKey, marketAsOfDate) {
  const rawHistory = Array.isArray(card?.priceHistory)
    ? card.priceHistory
    : Array.isArray(card?.price_history)
    ? card.price_history
    : [];
  const points = rawHistory
    .map((point) => ({
      date: getHistoryDateKey(point?.date),
      value: toFiniteNumber(point?.marketPrice ?? point?.market_price ?? point?.price),
    }))
    .filter((point) => point.date);

  const preferredEndDate = getTopCardPreferredHistoryEndDate(card, selectedWindowKey, points);
  const canonicalEndDate = getHistoryDateKey(marketAsOfDate);
  // The canonical market date is a ceiling the per-card end may pull in but
  // never push past — no point is ever synthesized beyond the snapshot.
  const endDate =
    preferredEndDate && canonicalEndDate
      ? preferredEndDate < canonicalEndDate
        ? preferredEndDate
        : canonicalEndDate
      : preferredEndDate || canonicalEndDate;
  const bounded = endDate ? points.filter((point) => point.date <= endDate) : points;
  return forwardFillDailyHistoryThroughDate(bounded, {
    dateField: "date",
    valueKeys: ["value"],
    endDateKey: endDate,
  });
}

/**
 * One featured card plus a ranked list. The rank is the card's position in the
 * page's own price-descending Top Chase list, so "#1" means the same thing here
 * as it does on desktop.
 */
export function buildTopChaseModel(
  cards,
  { selectedWindowKey = "30D", marketAsOfDate = null, maxRows = MOBILE_TOP_CHASE_MAX_ROWS } = {}
) {
  const rows = (Array.isArray(cards) ? cards : []).slice(0, maxRows).map((card, index) => {
    const historyPoints = buildTopChaseHistory(card, selectedWindowKey, marketAsOfDate);
    const windowState = resolveTopCardWindowState({ card, historyPoints, selectedWindowKey });
    const amount = toFiniteNumber(windowState?.displayMovement?.amount);
    const percent = toFiniteNumber(windowState?.displayMovement?.percent);
    const price = readCardMarketPrice(card);
    return {
      key: String(card?.id || card?.cardId || card?.cardNumber || card?.name || index),
      canonicalCardId: String(card?.canonicalCardId || card?.canonical_card_id || card?.cardId || card?.card_id || card?.id || "").trim() || null,
      cardVariantId: String(card?.cardVariantId || card?.card_variant_id || "").trim() || null,
      rank: index + 1,
      name: String(card?.name || "Unknown card"),
      // Rarity is a real published field or it is nothing — never "N/A" filler
      // in the featured slot, where an empty sublabel simply collapses.
      rarity: String(card?.rarity || "").trim() || null,
      cardNumber: String(card?.cardNumber || card?.card_number || "").trim() || null,
      imageUrl: readCardImageUrl(card),
      initials: getCardInitials(card?.name),
      price,
      priceText: formatMoney(price),
      amount,
      amountText: amount === null ? null : `${amount >= 0 ? "+" : "−"}${currency.format(Math.abs(amount))}`,
      percent,
      percentText: formatSignedPercent(percent),
      direction: directionOf(amount, percent),
      hasMovement: amount !== null || percent !== null,
    };
  });

  return { featured: rows[0] || null, ranked: rows.slice(1), rows, total: rows.length };
}

/** Canonical sealed ranking: the ten highest current product snapshot prices. */
export function buildTopSealedModel(products, { selectedWindowKey = "7D", maxRows = MOBILE_TOP_CHASE_MAX_ROWS } = {}) {
  const rows = sortSealedProductsByCurrentPrice(products).slice(0, maxRows).map((product, index) => {
    const window = selectSealedWindow(product, selectedWindowKey);
    const amount = toFiniteNumber(window?.movement?.amount ?? window?.movement?.amountChange);
    const percent = toFiniteNumber(window?.movement?.percent ?? window?.movement?.percentChange);
    const price = toFiniteNumber(product?.currentPrice);
    const name = String(product?.name || compactSealedProductLabel(product) || "Sealed product");
    return {
      key: String(product?.sealedProductId || product?.id || name || index),
      // Distinct from `key`, which falls back to name/index for a row-list
      // identity. A route must never be guessed from that fallback, so this is
      // null whenever the product carries no real canonical id.
      sealedProductId: product?.sealedProductId ? String(product.sealedProductId) : null,
      rank: index + 1,
      name,
      rarity: compactSealedProductLabel(product),
      imageUrl: product?.imageUrl || product?.image_url || null,
      initials: getCardInitials(name),
      price,
      priceText: formatMoney(price),
      amount,
      amountText: amount === null ? null : `${amount >= 0 ? "+" : "−"}${currency.format(Math.abs(amount))}`,
      percent,
      percentText: formatSignedPercent(percent),
      direction: directionOf(amount, percent),
      hasMovement: amount !== null || percent !== null,
    };
  });
  return { featured: rows[0] || null, ranked: rows.slice(1), rows, total: rows.length };
}

// --- Sealed Market ----------------------------------------------------------

/**
 * Product-switch chips. Only real products for this set are returned, in the
 * price-descending order the caller already established, so a set with one
 * sealed product yields one chip and a set with none yields an empty array.
 *
 * DISAMBIGUATION. `compactSealedProductLabel` names a product by family plus an
 * optional variant, so two distinct products with the same family and no
 * variant label both come back as (say) "ETB". A dropdown can live with that
 * because it also prints each option's price; a chip row cannot — two
 * identically-named chips are simply two chips the reader cannot choose
 * between. Where a label collides, the chip appends that product's own current
 * price. Nothing is invented: an unpriced colliding product falls back to its
 * published full name, and a unique label is never decorated.
 */
export function buildSealedProductChips(products) {
  const list = (Array.isArray(products) ? products : []).filter(Boolean);
  const labelCounts = new Map();
  for (const product of list) {
    const label = compactSealedProductLabel(product);
    labelCounts.set(label, (labelCounts.get(label) || 0) + 1);
  }

  return list.map((product) => {
    const label = compactSealedProductLabel(product);
    const priceText = formatMoney(product.currentPrice);
    const collides = (labelCounts.get(label) || 0) > 1;
    const fullName = String(product.name || "").trim();
    return {
      id: String(product.sealedProductId),
      label: !collides ? label : priceText ? `${label} · ${priceText}` : fullName || label,
      family: String(product.productFamily || "").trim() || null,
      priceText,
    };
  });
}

/**
 * The metrics strip under the sealed chart. ONLY the four readings the sealed
 * snapshot actually publishes: the window's low and high, how many observed
 * days back it, and the set's sealed product count. Population, market cap and
 * print-run figures are not in this contract, so no cell is emitted for them.
 * Every entry whose value resolves to null is dropped by the caller.
 */
export function buildSealedMetrics({ history, windowLabel, productCount } = {}) {
  const values = (Array.isArray(history) ? history : [])
    .map((point) => toFiniteNumber(point?.marketPrice))
    .filter((value) => value !== null && value > 0);
  const label = String(windowLabel || "").trim();
  const scope = label ? `${label === "lifetime" ? "LT" : label} ` : "";

  return [
    { key: "low", label: `${scope}Low`.trim(), value: values.length ? formatMoney(Math.min(...values)) : null },
    { key: "high", label: `${scope}High`.trim(), value: values.length ? formatMoney(Math.max(...values)) : null },
    { key: "points", label: "Observed Days", value: formatCount(values.length) },
    { key: "products", label: "Tracked Products", value: formatCount(productCount) },
  ].filter((metric) => metric.value !== null);
}

// --- Hero -------------------------------------------------------------------

/**
 * The hero's compact metric row. Release date, total cards and RIP rank are the
 * three the persistent desktop header already publishes; each is independently
 * omitted when the set does not carry it, so the row shrinks rather than
 * printing an em dash for data that does not exist.
 */
export function buildHeroMetrics({ releaseDateText, totalCards, ripRank, ripCohortSize } = {}) {
  const rank = toFiniteNumber(ripRank);
  const cohort = toFiniteNumber(ripCohortSize);
  return [
    { key: "release", label: "Released", value: String(releaseDateText || "").trim() || null },
    { key: "cards", label: "Total Cards", value: formatCount(totalCards) },
    {
      key: "rip",
      label: "RIP Rank",
      value: rank === null ? null : `#${Math.round(rank)}`,
      suffix: rank !== null && cohort !== null && cohort > 0 ? `of ${Math.round(cohort)}` : null,
    },
  ].filter((metric) => metric.value !== null);
}
