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

/**
 * ENTERTAINMENT COST — read, never computed.
 *
 * The backend publishes every field of this block already rounded, already
 * signed and already explicit about availability (see
 * `backend/domain/pokemon/entertainment_cost.py`). This function ONLY renames
 * `entertainmentCostPerPackEquivalent` to a shorter key and coerces types. It
 * deliberately does NOT compute `purchasePrice - expectedValue`, and it does
 * NOT divide the cost by `packCount`:
 *
 *   * the arithmetic looks trivial and is not — a Stage 2 product's stored
 *     expected value already contains its guaranteed promo, and the per-pack
 *     divisor is the modeled pack count, not the SKU's advertised one;
 *   * a frontend copy of the formula is a second implementation that can drift
 *     from the canonical one without any test noticing.
 *
 * `available` is deliberately stricter than the backend flag alone: a block
 * that claims availability without a number is not renderable as one.
 *
 * NEGATIVES SURVIVE. A product whose modeled contents are worth more than its
 * price has a negative entertainment cost. It is passed through unchanged: no
 * clamp to zero, no absolute value, no relabelling as profit.
 */
function normalizeEntertainmentCost(raw) {
  const block = isObject(raw) ? raw : {};
  const cost = number(block.entertainmentCost);
  return {
    contractPresent: isObject(raw),
    available: block.available === true && cost !== null,
    entertainmentCost: cost,
    perPack: number(block.entertainmentCostPerPackEquivalent),
    ratio: number(block.entertainmentCostRatio),
    purchasePrice: number(block.purchasePrice),
    expectedValue: number(block.expectedValue),
    packCount: number(block.packCount),
    // Preserved verbatim so explanatory copy can state the calculation basis
    // instead of assuming one.
    recoveryModel: text(block.recoveryModel),
    accessoryValueIncluded: block.accessoryValueIncluded === true,
    guaranteedComponentIncluded: block.guaranteedComponentIncluded === true,
    // Diagnostics only. The UI shows "Not modeled yet", never this string.
    reason: text(block.reason),
    contractVersion: text(block.contractVersion),
  };
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
    financialRipScore: number(row.financialRipScore),
    collectorAppealScore: number(row.collectorAppealScore),
    overallRipScore: number(row.overallRipScore),
    priceAsOf: text(row.priceAsOf),
    priceSource: text(row.priceSource),
    composition: isObject(row.composition) ? row.composition : null,
    availability: isObject(row.availability) ? row.availability : null,
    entertainmentCost: normalizeEntertainmentCost(row.entertainmentCost),
  };
}

function normalizeUnsupportedProduct(row, index) {
  if (!isObject(row)) return null;
  const product = normalizeProduct(row, index);
  if (!product) return null;
  return {
    ...product,
    available: false,
    reason: text(row.entertainmentCost?.reason) || text(row.availability?.reason),
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
    canonicalCardId: text(raw.canonicalCardId) || text(raw.cardId),
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
      unsupportedProducts: { contractVersion: null, productCount: 0, products: [] },
      topChase: null,
      comparisonScope: COMPARISON_SCOPE_WITHIN_FAMILY,
      crossFormatComparable: false,
    };
  }

  const available = ripDecision.currentRunAvailable === true;
  const sealed = isObject(ripDecision.sealedProducts) ? ripDecision.sealedProducts : {};
  const unsupported = isObject(ripDecision.unsupportedProducts) ? ripDecision.unsupportedProducts : {};

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
    unsupportedProducts: {
      contractVersion: text(unsupported.contractVersion),
      productCount: number(unsupported.productCount) ?? 0,
      products: (Array.isArray(unsupported.products) ? unsupported.products : [])
        .map(normalizeUnsupportedProduct)
        .filter(Boolean),
    },
    topChase: available ? normalizeTopChase(ripDecision.topChase) : null,
    // Republished verbatim so the UI can assert the policy it is bound by
    // instead of assuming it.
    comparisonScope: text(ripDecision.comparisonScope) || COMPARISON_SCOPE_WITHIN_FAMILY,
    crossFormatComparable: ripDecision.crossFormatComparable === true,
  };
}

export function selectDecisionProductsForFamily(decision, family) {
  const products = Array.isArray(decision?.products) ? decision.products : [];
  const canonicalFamily = text(family);
  return canonicalFamily ? products.filter((product) => product.family === canonicalFamily) : products;
}

export function selectDecisionProductById(decision, sealedProductId) {
  const canonicalId = text(sealedProductId);
  if (!canonicalId) return null;
  return (Array.isArray(decision?.products) ? decision.products : [])
    .find((product) => product.sealedProductId === canonicalId) || null;
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
 * spend.
 *
 * Returns a price only when the answer is UNAMBIGUOUS: exactly one priced
 * single-pack SKU. Zero gives `null`, and so does more than one.
 *
 * The contract is SKU-level, so a set can publish two differently-priced
 * single-pack SKUs. Taking the first row would make "gross pack spend at
 * today's pack price" silently mean "at one of today's two pack prices,
 * whichever the query happened to order first". We have not defined a canonical
 * loose-pack quote across multiple SKUs, so this refuses to invent one —
 * picking the cheapest, highest, average or first would each be a different
 * undeclared policy. The Chase UI already omits the spend line on `null`.
 */
export function selectLoosePackMarketPrice(products) {
  const packs = (Array.isArray(products) ? products : []).filter(
    (product) => product && product.packCount === 1 && product.marketPrice !== null
  );
  return packs.length === 1 ? packs[0].marketPrice : null;
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
