import { getStandardDeltaWindowDefinitions } from "../../../../lib/explore/marketDeltaWindows.mjs";

export const SEALED_MARKET_WINDOWS = Object.freeze(getStandardDeltaWindowDefinitions());

const FAMILY_LABELS = {
  booster_box: "Booster Box",
  enhanced_booster_box: "Enhanced Booster Box",
  elite_trainer_box: "ETB",
  pokemon_center_elite_trainer_box: "PC ETB",
  booster_bundle: "Booster Bundle",
  booster_pack: "Booster Pack",
  sleeved_booster_pack: "Sleeved Pack",
};

export function compactSealedProductLabel(product) {
  const base = FAMILY_LABELS[product?.productFamily] || product?.productFamilyLabel || "Sealed Product";
  return product?.variantLabel ? `${base} — ${product.variantLabel}` : base;
}

function finiteCurrentPrice(product) {
  const price = Number(product?.currentPrice);
  return Number.isFinite(price) && price > 0 ? price : null;
}

/**
 * Order sealed products most expensive first. Prices are compared numerically,
 * never lexically ("422.60" would otherwise sort below "80.38"). Products with
 * no usable current price sort last, and ties break deterministically on the
 * concise label, then the full name, then the id.
 *
 * Returns a new array — the payload's own products array is never mutated,
 * because it is shared React state read by other selectors.
 */
export function sortSealedProductsByCurrentPrice(products) {
  const list = Array.isArray(products) ? products.filter(Boolean) : [];
  return [...list].sort((a, b) => {
    const priceA = finiteCurrentPrice(a);
    const priceB = finiteCurrentPrice(b);
    if (priceA !== priceB) {
      if (priceA === null) return 1;
      if (priceB === null) return -1;
      return priceB - priceA;
    }
    return compactSealedProductLabel(a).localeCompare(compactSealedProductLabel(b))
      || String(a?.name || "").localeCompare(String(b?.name || ""))
      || String(a?.sealedProductId || "").localeCompare(String(b?.sealedProductId || ""));
  });
}

export function selectSealedProduct(payload, selectedId) {
  const products = Array.isArray(payload?.products) ? payload.products : [];
  const explicit = products.find((item) => String(item.sealedProductId) === String(selectedId));
  if (explicit) return explicit;

  // Price order wins over payload.defaultProductId so an older snapshot still
  // showcases the most expensive product. The stored default is only a
  // fallback for the case where no product carries a usable current price.
  const byPrice = sortSealedProductsByCurrentPrice(products);
  return byPrice.find((item) => finiteCurrentPrice(item) !== null)
    || products.find((item) => String(item.sealedProductId) === String(payload?.defaultProductId))
    || byPrice[0]
    || null;
}

function roundContractNumber(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function normalizeDatedPriceHistory(history) {
  const byDate = new Map();
  for (const point of Array.isArray(history) ? history : []) {
    const date = String(point?.date || "").slice(0, 10);
    const marketPrice = Number(point?.marketPrice);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(marketPrice) || marketPrice <= 0) continue;
    byDate.set(date, { ...point, date, marketPrice });
  }
  return [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export function deriveOneDayMovementFromHistory(history) {
  const valid = normalizeDatedPriceHistory(history);
  const latest = valid.at(-1);
  const previous = valid.slice(0, -1).reverse().find((point) => point.date < latest?.date);
  if (!latest || !previous) return null;

  const amount = roundContractNumber(latest.marketPrice - previous.marketPrice);
  const percent = roundContractNumber(amount / previous.marketPrice * 100);
  return {
    status: "available",
    comparisonStatus: "legacy_history_derived",
    requestedStartDate: previous.date,
    actualStartDate: previous.date,
    endDate: latest.date,
    startPrice: previous.marketPrice,
    endPrice: latest.marketPrice,
    currentPrice: latest.marketPrice,
    amount,
    amountChange: amount,
    percent,
    percentChange: percent,
    historyPointCount: 2,
    fullWindowCoverage: true,
    coverageDays: 1,
  };
}

export function getDisplayedTrendDirection(movement) {
  const finiteOrNull = (value) => value === null || value === undefined || value === "" || !Number.isFinite(Number(value))
    ? null
    : Number(value);
  const percent = finiteOrNull(movement?.percent);
  const amount = finiteOrNull(movement?.amount);
  const displayedDelta = Number.isFinite(percent) ? percent : Number.isFinite(amount) ? amount : null;
  if (displayedDelta === null || displayedDelta === 0) return "neutral";
  return displayedDelta > 0 ? "positive" : "negative";
}

export function selectSealedWindow(product, windowKey = "30D") {
  const requestedWindowKey = windowKey === "LT" ? "lifetime" : windowKey;
  const movements = product?.movements || {};
  const history = Array.isArray(product?.history) ? product.history : [];
  const preparedOneDay = movements["1D"];
  const validPreparedOneDay = preparedOneDay?.status === "available"
    && preparedOneDay.actualStartDate
    && preparedOneDay.endDate;
  const legacyOneDay = validPreparedOneDay ? null : deriveOneDayMovementFromHistory(history);
  const getMovement = (key) => (
    key === "1D"
      ? (validPreparedOneDay ? preparedOneDay : legacyOneDay)
      : movements[key] || (key === "lifetime" ? movements.LT : null) || null
  );
  const fallbackChains = {
    "1D": ["1D"],
    "7D": ["7D", "1D"],
    "30D": ["30D", "7D", "1D"],
    "3M": ["3M", "30D", "7D", "1D"],
    "6M": ["6M", "3M", "30D", "7D", "1D"],
    "1Y": ["1Y", "6M", "3M", "30D", "7D", "1D"],
    lifetime: ["1Y", "6M", "3M", "30D", "7D", "1D"],
  };
  const isFullySupported = (key) => {
    const candidate = getMovement(key);
    if (!candidate || candidate.status !== "available") return false;
    if (!candidate.actualStartDate || !candidate.endDate) return false;
    if (key === "1D") return true;
    if (candidate.fullWindowCoverage === true) return true;
    // Transitional v1 snapshots did not publish the explicit coverage flag.
    return candidate.fullWindowCoverage == null
      && candidate.comparisonStatus === "available"
      && candidate.actualStartDate
      && candidate.requestedStartDate
      && candidate.actualStartDate <= candidate.requestedStartDate;
  };
  let effectiveWindowKey;
  if (requestedWindowKey === "lifetime" && isFullySupported("1Y") && getMovement("lifetime")?.status === "available") {
    effectiveWindowKey = "lifetime";
  } else {
    effectiveWindowKey = (fallbackChains[requestedWindowKey] || [requestedWindowKey]).find(isFullySupported);
  }
  const lifetimeMovement = getMovement("lifetime");
  if (requestedWindowKey === "lifetime" && !effectiveWindowKey && lifetimeMovement?.status === "available") {
    effectiveWindowKey = "lifetime";
  }
  const movement = getMovement(effectiveWindowKey);
  const unavailableMovement = {
    status: "unavailable",
    comparisonStatus: "movement_unavailable",
    requestedStartDate: null,
    actualStartDate: null,
    endDate: product?.priceAsOf || null,
    historyPointCount: 0,
  };
  if (!movement || movement.status !== "available") {
    return {
      requestedWindowKey,
      effectiveWindowKey: effectiveWindowKey || requestedWindowKey,
      isFallback: Boolean(effectiveWindowKey && effectiveWindowKey !== requestedWindowKey),
      movement: unavailableMovement,
      history: [],
    };
  }
  if (effectiveWindowKey === "lifetime") {
    return {
      requestedWindowKey,
      effectiveWindowKey,
      isFallback: effectiveWindowKey !== requestedWindowKey,
      movement,
      history,
    };
  }
  const endDate = movement.endDate;
  const startDate = movement.actualStartDate || movement.requestedStartDate;
  if (!startDate || !endDate) {
    return {
      requestedWindowKey,
      effectiveWindowKey: effectiveWindowKey || requestedWindowKey,
      isFallback: Boolean(effectiveWindowKey && effectiveWindowKey !== requestedWindowKey),
      movement: unavailableMovement,
      history: [],
    };
  }
  const visibleHistory = effectiveWindowKey === "1D"
    ? normalizeDatedPriceHistory(history).filter((point) => point.date === startDate || point.date === endDate)
    : history.filter((point) => point.date >= startDate && point.date <= endDate);
  return {
    requestedWindowKey,
    effectiveWindowKey: effectiveWindowKey || requestedWindowKey,
    isFallback: Boolean(effectiveWindowKey && effectiveWindowKey !== requestedWindowKey),
    movement,
    history: visibleHistory,
  };
}
