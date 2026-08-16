/**
 * The ONE frontend boundary for `payload.ripDecision`.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * The backend publishes the decision contract in camelCase, already rounded and
 * already explicit about what is missing (see
 * `backend/db/services/rip_decision_service.py`). The previous decision-layer
 * attempt never read it: it guessed at `summary.decision_metrics` shapes that
 * the backend has never emitted, so every chase field resolved to `null` and the
 * page printed "not yet available" beside odds it was rendering elsewhere.
 *
 * So this adapter reads the contract's real key names, in one place. It does NOT
 * spread snake_case/camelCase fallbacks across the UI, and it does NOT invent a
 * value when one is absent.
 *
 * MISSING STAYS MISSING
 * ---------------------
 * `null` is a rendering instruction, not a number to coerce. A fabricated `0`
 * edge sits exactly on break-even, which is a specific and confident claim we do
 * not have the data to make. Callers branch on `null`; they never default it.
 *
 * NOTHING HERE RANKS
 * ------------------
 * Product order is the contract's order. `modelEdgePercent` is arithmetic on two
 * published numbers around a shared 0% reference — it is not a score, and
 * sorting by it would be the first half of a cross-format ranking that the
 * backend explicitly marks unvalidated (`crossFormatComparable: false`).
 */

const COMPARISON_SCOPE_WITHIN_FAMILY = "within_product_family_only";

/** A finite number, or `null`. Booleans and blank strings are not numbers. */
function number(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "boolean") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Non-empty trimmed text, or `null`. */
function text(value) {
  const string = String(value ?? "").trim();
  return string ? string : null;
}

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

/**
 * A product family key turned into a display label, used only when the contract
 * carries no human label of its own. Kept as a formatter rather than a registry
 * so a newly modeled family renders on the day the backend publishes it instead
 * of silently falling out of the table.
 */
function humanizeFamily(key) {
  const raw = text(key);
  if (!raw) return null;
  return raw
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((word) => {
      const lower = word.toLowerCase();
      if (lower === "etb") return "ETB";
      if (lower === "pc") return "PC";
      return lower.charAt(0).toUpperCase() + lower.slice(1);
    })
    .join(" ");
}

function normalizeProduct(row, index) {
  if (!isObject(row)) return null;
  const sealedProductId = text(row.sealedProductId);
  const productName = text(row.productName);
  const family = text(row.productFamily);
  if (!sealedProductId && !productName && !family) return null;

  return {
    // IDENTITY IS THE SKU, NOT THE FAMILY. The contract is SKU-level and
    // legitimately publishes several products of one family (multiple ETB
    // artwork SKUs, for instance). Keying on `productFamily` collapsed those
    // into duplicate React keys and made selecting one SKU resolve another.
    //
    // `index` is the last resort rather than the family so that a family with
    // two SKUs can never produce two identical keys.
    key: sealedProductId || `product-${index}`,
    sealedProductId,
    productName,
    // `order` is the contract's order (pack count ascending), never a rank.
    order: index,
    family,
    // The SKU's own name wins: two ETB SKUs must not both render as "ETB".
    label: productName || humanizeFamily(family) || `Product ${index + 1}`,
    packCount: number(row.packCount),
    marketPrice: number(row.marketPrice),
    modelBreakEvenPrice: number(row.modelBreakEvenPrice),
    modeledReturnPercent: number(row.modeledReturnPercent),
    modelEdgePercent: number(row.modelEdgePercent),
    typicalOpening: number(row.typicalOpening),
    chanceToRecoverCost: number(row.chanceToRecoverCost),
    priceAsOf: text(row.priceAsOf),
    priceSource: text(row.priceSource),
  };
}

function normalizeTopChase(raw) {
  if (!isObject(raw)) return null;
  const name = text(raw.cardName);
  const marketPrice = number(raw.currentMarketPrice);
  // A chase with neither an identity nor a price cannot be rendered as one.
  if (!name && marketPrice === null) return null;

  return {
    cardId: text(raw.cardId),
    cardVariantId: text(raw.cardVariantId),
    name,
    rarity: text(raw.rarity),
    imageUrl: text(raw.imageUrl) || text(raw.imageSmallUrl) || text(raw.imageLargeUrl),
    currentMarketPrice: marketPrice,
    modeledProbability: number(raw.modeledProbability),
    impliedOddsOneInN: number(raw.impliedOddsOneInN),
    packsFor50PercentChance: number(raw.packsFor50PercentChance),
    packsFor90PercentChance: number(raw.packsFor90PercentChance),
    sourceCalculationRunId: text(raw.sourceCalculationRunId),
  };
}

/**
 * Normalize `payload.ripDecision` for the RIP page.
 *
 * Returns a stable shape in every case, so callers branch on `available`
 * rather than on the presence of nested objects. A snapshot built before this
 * contract existed is reported as `contractPresent: false` — distinct from a
 * present contract that honestly has no current run.
 */
export function selectRipDecisionContract(ripDecision) {
  if (!isObject(ripDecision)) {
    return {
      contractPresent: false,
      available: false,
      sourceCalculationRunId: null,
      runStatus: null,
      products: [],
      productCount: 0,
      topChase: null,
      comparisonScope: COMPARISON_SCOPE_WITHIN_FAMILY,
      crossFormatComparable: false,
    };
  }

  const available = ripDecision.currentRunAvailable === true;
  const sealed = isObject(ripDecision.sealedProducts) ? ripDecision.sealedProducts : {};

  // Without a current run the page shows nothing economic. Rendering the
  // contract's (empty) product list is the point: falling back to older rows
  // would print correct-looking economics from a run the rest of the page is
  // not describing.
  const products = available
    ? (Array.isArray(sealed.products) ? sealed.products : [])
        .map(normalizeProduct)
        .filter(Boolean)
    : [];

  return {
    contractPresent: true,
    available,
    sourceCalculationRunId: text(ripDecision.sourceCalculationRunId),
    runStatus: text(sealed.runStatus),
    products,
    productCount: number(sealed.productCount) ?? products.length,
    topChase: available ? normalizeTopChase(ripDecision.topChase) : null,
    // Republished verbatim so the UI can assert the policy it is bound by
    // instead of assuming it.
    comparisonScope: text(ripDecision.comparisonScope) || COMPARISON_SCOPE_WITHIN_FAMILY,
    crossFormatComparable: ripDecision.crossFormatComparable === true,
  };
}

/**
 * The product whose economics the selected-product panel shows by default.
 *
 * This is deliberately "the first row the contract supplied", NOT "the best
 * one". Choosing by edge would rank formats the backend has not validated for
 * comparison, and would make the default silently change as prices move.
 */
export function defaultSelectedProductKey(products) {
  const list = Array.isArray(products) ? products : [];
  const priced = list.find((product) => product && product.marketPrice !== null);
  return (priced || list[0] || null)?.key ?? null;
}

/**
 * The loose-pack market price, used ONLY to express chase pack counts as gross
 * spend. Returns `null` when no single-pack product is modeled, in which case
 * the caller omits the spend line rather than guessing a price.
 */
export function selectLoosePackMarketPrice(products) {
  const list = Array.isArray(products) ? products : [];
  const pack = list.find((product) => product && product.packCount === 1 && product.marketPrice !== null);
  return pack ? pack.marketPrice : null;
}

/** Shared money/percent formatting for decision copy. */
function formatMoney(value) {
  return `$${Number(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatPercent(value) {
  return `${Math.round(Number(value) * 10) / 10}%`;
}

/**
 * The one-sentence reading of a product's model edge.
 *
 * `modelEdgePercent` is `(modelBreakEvenPrice / marketPrice - 1) * 100`, so its
 * denominator is ALWAYS the market price. Both signs must therefore be read the
 * same way: "modeled long-run opening value is N% above/below MARKET COST".
 *
 * Phrasing the positive case as "market price is N% below break-even" silently
 * re-bases the percentage on break-even and states a different number. At $100
 * market against a $110 break-even the edge is +10%, but the market price is
 * 9.09% below break-even — not 10%. One published percentage, one denominator,
 * and no second metric invented to paper over the mismatch.
 */
export function buildEdgeSentence(product) {
  const edge = product?.modelEdgePercent ?? null;
  const marketPrice = product?.marketPrice ?? null;
  if (edge === null || marketPrice === null) return null;
  if (edge === 0) {
    return `Today's ${formatMoney(marketPrice)} price sits exactly at modeled break-even.`;
  }
  const direction = edge > 0 ? "above" : "below";
  return `At today's ${formatMoney(marketPrice)} price, modeled long-run opening value is ${formatPercent(Math.abs(edge))} ${direction} market cost.`;
}

/**
 * Axis geometry for the break-even visual.
 *
 * 0% is market price EQUALS model break-even. Negative edge means today's market
 * price is above modeled long-run opening value; positive means below. The
 * domain is symmetric around zero so that equal magnitudes are equally long on
 * both sides — an asymmetric axis would make a -4% product look worse or better
 * than a +4% one purely through scaling.
 */
export function buildBreakEvenAxis(products, { minimumDomain = 10 } = {}) {
  const edges = (Array.isArray(products) ? products : [])
    .map((product) => product?.modelEdgePercent)
    .filter((edge) => typeof edge === "number" && Number.isFinite(edge));

  const largest = edges.reduce((max, edge) => Math.max(max, Math.abs(edge)), 0);
  const domain = Math.max(minimumDomain, Math.ceil(largest / 5) * 5);

  return {
    domain,
    /**
     * Percent-of-width position for one edge value, where 50 is break-even.
     * `null` in stays `null` out: an unavailable edge has no position on the
     * axis and must not be drawn sitting on zero.
     */
    positionFor(edge) {
      if (typeof edge !== "number" || !Number.isFinite(edge)) return null;
      const clamped = Math.max(-domain, Math.min(domain, edge));
      return 50 + (clamped / domain) * 50;
    },
  };
}
