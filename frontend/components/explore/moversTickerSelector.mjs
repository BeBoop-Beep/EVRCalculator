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

  if (percent === null) return null;
  return {
    amount,
    percent,
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
    card?.cardId ??
      card?.card_id ??
      card?.id ??
      card?.pokemonTcgApiCardId ??
      card?.pokemon_tcg_api_card_id ??
      `${card?.name || "unknown"}:${card?.setNumber || card?.set_number || card?.cardNumber || card?.card_number || ""}`
  );
}

function rankedSide(cards, direction) {
  return (Array.isArray(cards) ? cards : [])
    .map((card) => ({ card, movement: getCardMovement7d(card), identity: stableCardIdentity(card) }))
    .filter(({ movement }) => movement && (direction === "gainer" ? movement.percent > 0 : movement.percent < 0))
    .sort(
      (left, right) =>
        Math.abs(right.movement.percent) - Math.abs(left.movement.percent) ||
        left.identity.localeCompare(right.identity)
    );
}

export function selectMoversTickerItems(entry, { perSide = 5, maxItems = 10 } = {}) {
  const gainers = rankedSide(entry?.heatingUp ?? entry?.heating_up, "gainer");
  const decliners = rankedSide(entry?.coolingOff ?? entry?.cooling_off, "decliner");
  const selected = [];
  const seen = new Set();

  const add = (item) => {
    if (!item || seen.has(item.identity) || selected.length >= maxItems) return;
    seen.add(item.identity);
    selected.push({ card: item.card, movement: item.movement });
  };

  gainers.slice(0, perSide).forEach(add);
  decliners.slice(0, perSide).forEach(add);

  if (selected.length < maxItems) {
    [...gainers.slice(perSide), ...decliners.slice(perSide)]
      .sort(
        (left, right) =>
          Math.abs(right.movement.percent) - Math.abs(left.movement.percent) ||
          left.identity.localeCompare(right.identity)
      )
      .forEach(add);
  }

  return selected.slice(0, maxItems);
}
