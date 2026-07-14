function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function getDeltaMapValue(card, fieldNames) {
  const maps = [card?.deltas, card?.deltaMap, card?.delta_map, card?.movementsByWindow, card?.movements_by_window];
  for (const map of maps) {
    const entry = map?.["7D"] ?? map?.["7d"] ?? map?.[7];
    if (entry === null || entry === undefined) continue;
    if (typeof entry !== "object") {
      const value = toFiniteNumber(entry);
      if (value !== null && fieldNames.includes("percent")) return value;
      continue;
    }
    for (const field of fieldNames) {
      const value = toFiniteNumber(entry?.[field]);
      if (value !== null) return value;
    }
  }
  return null;
}

export function getCardMovement7d(card) {
  const nested = card?.movement7d ?? card?.movement_7d ?? card?.movement?.["7D"] ?? card?.movement?.["7d"] ?? null;
  const percent =
    toFiniteNumber(card?.change7dPercent) ??
    toFiniteNumber(card?.change_7d_percent) ??
    toFiniteNumber(nested?.changePercent) ??
    toFiniteNumber(nested?.change_percent) ??
    toFiniteNumber(nested?.percent) ??
    toFiniteNumber(card?.changePercent) ??
    toFiniteNumber(card?.change_percent) ??
    toFiniteNumber(card?.movementPercent) ??
    toFiniteNumber(card?.movement_percent) ??
    getDeltaMapValue(card, ["changePercent", "change_percent", "percent"]);
  const amount =
    toFiniteNumber(card?.change7dAmount) ??
    toFiniteNumber(card?.change_7d_amount) ??
    toFiniteNumber(nested?.changeAmount) ??
    toFiniteNumber(nested?.change_amount) ??
    toFiniteNumber(nested?.amount) ??
    toFiniteNumber(card?.changeAmount) ??
    toFiniteNumber(card?.change_amount) ??
    getDeltaMapValue(card, ["changeAmount", "change_amount", "amount"]);

  // hasValidMovement: a finite amount OR percentage is enough — a card must
  // not be dropped just because one of the two fields is missing.
  if (percent === null && amount === null) return null;
  return {
    amount,
    percent,
    // Reliability/coverage stay as metadata for badges/tooltips — they never
    // decide ticker membership.
    reliable: nested?.reliable === undefined || nested?.reliable === null ? null : Boolean(nested.reliable),
    reliability: nested?.reliability ?? null,
    fullWindowCoverage: Boolean(nested?.fullWindowCoverage ?? nested?.full_window_coverage),
    isPartialWindow: Boolean(nested?.isPartialWindow ?? nested?.is_partial_window),
    windowCoverageDays: toFiniteNumber(nested?.windowCoverageDays ?? nested?.window_coverage_days),
    requestedWindowDays: toFiniteNumber(nested?.requestedWindowDays ?? nested?.requested_window_days) ?? 7,
  };
}

export function getMoversTickerTrendValue(movement) {
  const amount = toFiniteNumber(movement?.amount);
  if (amount !== null) return amount;
  return toFiniteNumber(movement?.percent);
}

function stableCardIdentity(card) {
  return String(
    card?.canonicalCardId ??
      card?.canonical_card_id ??
      card?.pokemonCanonicalCardId ??
      card?.pokemon_canonical_card_id ??
      card?.cardId ??
      card?.card_id ??
      card?.id ??
      card?.pokemonTcgApiCardId ??
      card?.pokemon_tcg_api_card_id ??
      `${card?.name || "unknown"}:${card?.setNumber || card?.set_number || card?.cardNumber || card?.card_number || ""}`
  );
}

function getCandidateCards(entry) {
  if (Array.isArray(entry?.all) && entry.all.length > 0) {
    return { cards: entry.all, authoritativeOrder: true };
  }
  if (Array.isArray(entry?.movements) && entry.movements.length > 0) {
    return { cards: entry.movements, authoritativeOrder: true };
  }
  return { cards: [
    ...(Array.isArray(entry?.heatingUp) ? entry.heatingUp : Array.isArray(entry?.heating_up) ? entry.heating_up : []),
    ...(Array.isArray(entry?.coolingOff) ? entry.coolingOff : Array.isArray(entry?.cooling_off) ? entry.cooling_off : []),
  ], authoritativeOrder: false };
}

function absoluteMovementValue(value) {
  const parsed = toFiniteNumber(value);
  return parsed === null ? 0 : Math.abs(parsed);
}

function hasNonzeroMovement(movement) {
  if (!movement) return false;
  const amount = toFiniteNumber(movement.amount);
  if (amount !== null && Math.abs(amount) > 0) return true;
  const percent = toFiniteNumber(movement.percent);
  return percent !== null && Math.abs(percent) > 0;
}

export const MOVERS_TICKER_MAX_ITEMS = 10;

export function selectMoversTickerItems(entry, { maxItems = MOVERS_TICKER_MAX_ITEMS } = {}) {
  const candidates = getCandidateCards(entry);
  // Membership is hasValidMovement + nonzero movement — an honest valid
  // movement always qualifies. Reliability / mover-eligibility / partial
  // window flags are metadata only and must never exclude a card here.
  const eligible = candidates.cards
    .map((card) => ({ card, movement: getCardMovement7d(card), identity: stableCardIdentity(card) }))
    .filter(({ movement }) => hasNonzeroMovement(movement));
  // Canonical ranking (matches Cards → Market Movers → Largest 7D Moves):
  // absolute dollar change desc, then absolute percent desc, then stable
  // canonical identity. Only used when the entry does not already carry the
  // authoritative canonical order (`all` from the canonical cards filter).
  const ranked = candidates.authoritativeOrder
    ? eligible
    : eligible.sort(
        (left, right) =>
          absoluteMovementValue(right.movement.amount) - absoluteMovementValue(left.movement.amount) ||
          absoluteMovementValue(right.movement.percent) - absoluteMovementValue(left.movement.percent) ||
          left.identity.localeCompare(right.identity)
      );
  const selected = [];
  const seen = new Set();

  for (const item of ranked) {
    if (seen.has(item.identity)) continue;
    seen.add(item.identity);
    selected.push({ card: item.card, movement: item.movement });
    if (selected.length >= maxItems) break;
  }

  return selected;
}
