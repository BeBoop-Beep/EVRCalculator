// Dedicated Top Chase payload contract.
//
// Why this module exists
// ----------------------
// The Top Chase section used to infer success from `cards.length > 0`. That is
// not the same question as "can this render". A checklist/dashboard fallback row
// carries an image and a price but no dedicated Top Chase history series, so the
// section rendered a full grid of cards in which every single chart said
// "Awaiting trend" — and the failed dedicated module was recorded as a success,
// so nothing ever retried.
//
// The distinction that matters is between a payload that is *settled* (a genuinely
// new set really does only have one price point) and one that is *broken* (a
// malformed or previous-generation snapshot row). Only the second should retry;
// only the first should be shown as a truthful terminal state. Everything here is
// pure so both the browser client and the tests can ask the same question.

export const TOP_CHASE_STATUS = Object.freeze({
  COMPLETE: "complete",
  INSUFFICIENT_HISTORY: "insufficient_history",
  STRUCTURALLY_INCOMPLETE: "structurally_incomplete",
  IDENTITY_MISMATCH: "identity_mismatch",
  EMPTY: "empty",
  TRANSPORT_FAILURE: "transport_failure",
});

// A chart needs two dated points to draw a line. One point is a dot, not a trend.
export const MIN_GRAPH_POINTS = 2;

// Statuses worth another attempt. `insufficient_history` and `empty` are settled
// truths about the data, not transport faults — retrying them only burns
// requests and never changes the answer.
const RETRYABLE_STATUSES = new Set([
  TOP_CHASE_STATUS.STRUCTURALLY_INCOMPLETE,
  TOP_CHASE_STATUS.IDENTITY_MISMATCH,
  TOP_CHASE_STATUS.TRANSPORT_FAILURE,
]);

export function isRetryableTopChaseStatus(status) {
  return RETRYABLE_STATUSES.has(status);
}

function normalizeIdentity(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
}

function isValidDateKey(value) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(value ?? "").slice(0, 10));
}

function toDateKey(value) {
  const text = String(value ?? "").slice(0, 10);
  return isValidDateKey(text) ? text : null;
}

function toFinitePrice(value) {
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

/**
 * Valid, dated price points for one card, sorted ascending.
 * A point without a parseable date or a finite price cannot be plotted.
 */
export function usableHistoryPoints(history) {
  return (Array.isArray(history) ? history : [])
    .map((point) => {
      const date = toDateKey(point?.date);
      const price = toFinitePrice(point?.marketPrice ?? point?.market_price ?? point?.price);
      return date && price !== null ? { date, price } : null;
    })
    .filter(Boolean)
    .sort((a, b) => a.date.localeCompare(b.date));
}

function cardIdentity(card) {
  return (
    card?.cardVariantId ??
    card?.card_variant_id ??
    card?.cardId ??
    card?.card_id ??
    card?.id ??
    null
  );
}

/**
 * Validate a normalized dedicated Top Chase payload.
 *
 * Returns a structured verdict rather than a boolean so callers can tell a new
 * set apart from a broken snapshot, and so the last-known-good cache only ever
 * stores payloads that were genuinely complete.
 */
export function validateTopChasePayload(payload, options = {}) {
  const { setId = null, window = null, limit = null } = options;
  const minGraphPoints = Number.isFinite(options.minGraphPoints)
    ? options.minGraphPoints
    : MIN_GRAPH_POINTS;

  const reasons = [];
  const base = {
    window: window ?? null,
    limit: limit ?? null,
    cardCount: 0,
    pricedCardCount: 0,
    renderableCardCount: 0,
    maxHistoryPoints: 0,
    latestMarketDate: null,
    reasons,
  };

  if (!payload || typeof payload !== "object") {
    reasons.push("missing_payload");
    return { ...base, status: TOP_CHASE_STATUS.STRUCTURALLY_INCOMPLETE, renderable: false, complete: false, retryable: true };
  }

  const latestMarketDate = toDateKey(payload?.latestMarketDate ?? payload?.latest_market_date);
  base.latestMarketDate = latestMarketDate;

  // --- Identity -------------------------------------------------------------
  // A payload for a different set must never be rendered under this one, and a
  // payload whose identity cannot be verified is treated as unusable rather than
  // trusted (fail-closed).
  const requested = normalizeIdentity(setId);
  // Retained beyond the identity block below: the per-card cross-set check needs
  // the SAME verified candidate list, not the caller's identifier form. See the
  // cross-set section for why.
  let identityCandidates = [];
  if (requested) {
    const candidates = [payload?.set?.id, payload?.set?.slug, payload?.set?.canonicalKey, payload?.set?.canonical_key]
      .filter((value) => value !== null && value !== undefined && String(value).trim() !== "")
      .map(normalizeIdentity);
    identityCandidates = candidates;

    if (candidates.length === 0) {
      reasons.push("identity_unverifiable");
      return { ...base, status: TOP_CHASE_STATUS.IDENTITY_MISMATCH, renderable: false, complete: false, retryable: true };
    }
    if (!candidates.includes(requested)) {
      reasons.push("set_identity_mismatch");
      return { ...base, status: TOP_CHASE_STATUS.IDENTITY_MISMATCH, renderable: false, complete: false, retryable: true };
    }
  }

  const cards = Array.isArray(payload?.cards) ? payload.cards : [];
  base.cardCount = cards.length;

  if (cards.length === 0) {
    reasons.push("no_top_chase_cards");
    return { ...base, status: TOP_CHASE_STATUS.EMPTY, renderable: false, complete: false, retryable: false };
  }

  // --- Cross-set history ----------------------------------------------------
  // A card carrying a different set's id means the row was assembled from the
  // wrong source. This is never renderable under the requested set.
  //
  // Compare against the payload's OWN verified identity candidates, not against
  // `requested`. Callers legitimately ask by different identifier forms — the
  // set page asks by slug ("ascendedheroes") while cards carry the set UUID
  // ("75cd439d-...") — so `cardSetId !== requested` classified every card of a
  // perfectly healthy payload as foreign. That produced a spurious, retryable
  // IDENTITY_MISMATCH on every single Top Chase load, which cost a second
  // identical ~542 kB request and then failed again. The block above has already
  // proven `payload.set` IS the requested set, so its candidate list is the
  // correct basis for comparison; `requested` is included too, so a payload
  // whose `set` echoes only the caller's form still matches. A card from a
  // genuinely different set is still caught — neither its UUID nor its slug
  // appears among these candidates.
  if (requested) {
    const allowedSetIdentities = new Set([...identityCandidates, requested]);
    const foreign = cards.find((card) => {
      const cardSetId = normalizeIdentity(card?.setId ?? card?.set_id);
      return cardSetId && !allowedSetIdentities.has(cardSetId);
    });
    if (foreign) {
      reasons.push("cross_set_card_history");
      return { ...base, status: TOP_CHASE_STATUS.IDENTITY_MISMATCH, renderable: false, complete: false, retryable: true };
    }
  }

  // --- Per-card structural quality -----------------------------------------
  let pricedCardCount = 0;
  let renderableCardCount = 0;
  let maxHistoryPoints = 0;
  let sawFutureDate = false;
  let sawMissingIdentity = false;

  cards.forEach((card) => {
    if (cardIdentity(card) === null) {
      sawMissingIdentity = true;
      return;
    }

    const price = toFinitePrice(card?.marketPrice ?? card?.market_price ?? card?.currentPrice ?? card?.current_price);
    if (price === null || price <= 0) {
      return;
    }
    pricedCardCount += 1;

    const points = usableHistoryPoints(card?.priceHistory ?? card?.price_history);
    if (latestMarketDate && points.some((point) => point.date > latestMarketDate)) {
      sawFutureDate = true;
      return;
    }

    maxHistoryPoints = Math.max(maxHistoryPoints, points.length);
    if (points.length >= minGraphPoints) {
      renderableCardCount += 1;
    }
  });

  base.pricedCardCount = pricedCardCount;
  base.renderableCardCount = renderableCardCount;
  base.maxHistoryPoints = maxHistoryPoints;

  if (sawMissingIdentity) {
    reasons.push("card_missing_stable_identity");
  }
  if (sawFutureDate) {
    reasons.push("history_date_after_latest_market_date");
    return { ...base, status: TOP_CHASE_STATUS.STRUCTURALLY_INCOMPLETE, renderable: false, complete: false, retryable: true };
  }

  if (pricedCardCount === 0) {
    reasons.push("no_card_with_valid_price");
    return { ...base, status: TOP_CHASE_STATUS.STRUCTURALLY_INCOMPLETE, renderable: false, complete: false, retryable: true };
  }

  if (renderableCardCount === pricedCardCount && !sawMissingIdentity) {
    return { ...base, status: TOP_CHASE_STATUS.COMPLETE, renderable: true, complete: true, retryable: false };
  }

  // Priced cards exist but none can draw a line. Zero points anywhere is the
  // signature of a checklist/dashboard fallback or a malformed row; one point is
  // a genuinely new set that simply has not accumulated history yet.
  if (maxHistoryPoints === 0) {
    reasons.push("no_usable_top_chase_history");
    return { ...base, status: TOP_CHASE_STATUS.STRUCTURALLY_INCOMPLETE, renderable: false, complete: false, retryable: true };
  }

  if (maxHistoryPoints < minGraphPoints) {
    reasons.push("insufficient_history_for_trend");
    return { ...base, status: TOP_CHASE_STATUS.INSUFFICIENT_HISTORY, renderable: false, complete: false, retryable: false };
  }

  // Some cards graph and some do not: renderable, but not clean enough to store
  // as last-known-good or to beat a complete row during backend row selection.
  reasons.push("partial_top_chase_history");
  return { ...base, status: TOP_CHASE_STATUS.STRUCTURALLY_INCOMPLETE, renderable: true, complete: false, retryable: true };
}

/** Structural quality score used to rank two equally fresh snapshot rows. */
export function topChaseQualityScore(verdict) {
  if (!verdict) {
    return -1;
  }
  if (verdict.status === TOP_CHASE_STATUS.COMPLETE) {
    return 1000 + verdict.renderableCardCount;
  }
  if (verdict.renderable) {
    return 500 + verdict.renderableCardCount;
  }
  if (verdict.status === TOP_CHASE_STATUS.INSUFFICIENT_HISTORY) {
    return 100;
  }
  return 0;
}
