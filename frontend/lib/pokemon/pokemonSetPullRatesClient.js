function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

async function readJsonResponse(response, fallbackMessage) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message = payload?.message || payload?.error || fallbackMessage;
    const requestError = new Error(message);
    requestError.status = response.status;
    requestError.code = payload?.code;
    throw requestError;
  }

  return payload;
}

function normalizePullRateRow(row) {
  if (!row || typeof row !== "object") {
    return row;
  }
  return {
    ...row,
    rarity: toOptionalString(row.rarity),
    slotLabel: toOptionalString(row.slotLabel ?? row.slot_label),
    group: toOptionalString(row.group),
    cardCount: toOptionalNumber(row.cardCount ?? row.card_count ?? row.eligibleCardCount ?? row.eligible_card_count),
    specificCardOddsDenominator: toOptionalNumber(
      row.specificCardOddsDenominator ?? row.specific_card_odds_denominator
    ),
    expectedCardsPerPack: toOptionalNumber(row.expectedCardsPerPack ?? row.expected_cards_per_pack),
    rarityOddsDenominator: toOptionalNumber(row.rarityOddsDenominator ?? row.rarity_odds_denominator),
  };
}

function normalizePullRateAssumptions(source) {
  if (!source || typeof source !== "object") {
    return null;
  }
  const groups = Array.isArray(source.groups)
    ? source.groups.map((group) => ({
        key: toOptionalString(group?.key),
        label: toOptionalString(group?.label),
        rows: Array.isArray(group?.rows) ? group.rows.map(normalizePullRateRow) : [],
      }))
    : [];
  const rows = Array.isArray(source.rows) ? source.rows.map(normalizePullRateRow) : [];
  return { ...source, groups, rows };
}

export function normalizePokemonSetPullRatesPayload(payload) {
  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug ?? payload?.set?.canonicalKey),
    },
    pullRateAssumptions: normalizePullRateAssumptions(payload?.pullRates ?? payload?.pull_rates),
    packPaths: Array.isArray(payload?.packPaths) ? payload.packPaths : [],
    rarityBuckets: Array.isArray(payload?.rarityBuckets) ? payload.rarityBuckets : [],
    assumptions: payload?.assumptions && typeof payload.assumptions === "object" ? payload.assumptions : {},
    sources: Array.isArray(payload?.sources) ? payload.sources : [],
    meta: payload?.meta || { warnings: [] },
  };
}

export async function getPokemonSetPullRates(setId) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const response = await fetch(`/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/pull-rates`, {
    method: "GET",
  });

  return normalizePokemonSetPullRatesPayload(
    await readJsonResponse(response, "Unable to load pull rate assumptions")
  );
}
