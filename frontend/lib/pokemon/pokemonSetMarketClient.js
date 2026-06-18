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

function normalizeDateKey(value) {
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }
  if (/^\d{4}-\d{2}-\d{2}/.test(text)) {
    return text.slice(0, 10);
  }
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return text.slice(0, 10) || null;
  }
  return date.toISOString().slice(0, 10);
}

function normalizeDailyPriceHistory(history) {
  const dailyPoints = new Map();

  (Array.isArray(history) ? history : []).forEach((point) => {
    const date = normalizeDateKey(point?.date ?? point?.capturedAt ?? point?.captured_at);
    const marketPrice = toOptionalNumber(point?.marketPrice ?? point?.market_price ?? point?.price);
    if (!date) {
      return;
    }
    dailyPoints.set(date, {
      date,
      marketPrice,
      source: toOptionalString(point?.source ?? point?.provider),
      provider: toOptionalString(point?.provider ?? point?.source),
      conditionId: toOptionalString(point?.conditionId ?? point?.condition_id),
      condition_id: toOptionalString(point?.condition_id ?? point?.conditionId),
      isCarriedForward: Boolean(point?.isCarriedForward ?? point?.is_carried_forward),
      is_carried_forward: Boolean(point?.is_carried_forward ?? point?.isCarriedForward),
      sourceDate: toOptionalString(point?.sourceDate ?? point?.source_date),
      source_date: toOptionalString(point?.source_date ?? point?.sourceDate),
    });
  });

  return Array.from(dailyPoints.values()).sort((a, b) => a.date.localeCompare(b.date));
}

function normalizeDailySetValueHistory(history) {
  const dailyPoints = new Map();

  (Array.isArray(history) ? history : []).forEach((point) => {
    const date = normalizeDateKey(point?.date);
    const setValue = toOptionalNumber(point?.setValue ?? point?.set_value);
    if (!date) {
      return;
    }
    dailyPoints.set(date, {
      date,
      setValue,
      cardCountPriced: toOptionalNumber(point?.cardCountPriced ?? point?.card_count_priced),
      source: toOptionalString(point?.source ?? point?.provider),
      provider: toOptionalString(point?.provider ?? point?.source),
      calculationRunId: toOptionalString(point?.calculationRunId ?? point?.calculation_run_id),
      calculation_run_id: toOptionalString(point?.calculation_run_id ?? point?.calculationRunId),
      isCarriedForward: Boolean(point?.isCarriedForward ?? point?.is_carried_forward),
      is_carried_forward: Boolean(point?.is_carried_forward ?? point?.isCarriedForward),
      sourceDate: toOptionalString(point?.sourceDate ?? point?.source_date),
      source_date: toOptionalString(point?.source_date ?? point?.sourceDate),
    });
  });

  return Array.from(dailyPoints.values()).sort((a, b) => a.date.localeCompare(b.date));
}

function normalizeTopMarketCardsPayload(payload) {
  const cards = Array.isArray(payload?.cards) ? payload.cards : [];

  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug),
    },
    cards: cards.map((card) => {
      const priceHistory = normalizeDailyPriceHistory(
        Array.isArray(card?.priceHistory) ? card.priceHistory : Array.isArray(card?.price_history) ? card.price_history : []
      );

      return {
        id: toOptionalString(card?.cardId ?? card?.card_id ?? card?.id),
        cardId: toOptionalString(card?.cardId ?? card?.card_id ?? card?.id),
        cardVariantId: toOptionalString(card?.cardVariantId ?? card?.card_variant_id),
        setId: toOptionalString(card?.setId ?? card?.set_id),
        name: toOptionalString(card?.name),
        imageUrl: toOptionalString(card?.imageUrl ?? card?.image_url),
        imageSmallUrl: toOptionalString(card?.imageSmallUrl ?? card?.image_small_url),
        imageLargeUrl: toOptionalString(card?.imageLargeUrl ?? card?.image_large_url),
        rarity: toOptionalString(card?.rarity),
        setNumber: toOptionalString(card?.setNumber ?? card?.set_number),
        cardNumber: toOptionalString(card?.setNumber ?? card?.set_number),
        estimatedMarketPrice: toOptionalNumber(card?.estimatedMarketPrice ?? card?.estimated_market_price),
        marketPrice: toOptionalNumber(card?.marketPrice ?? card?.estimatedMarketPrice ?? card?.estimated_market_price),
        priceUpdatedAt: toOptionalString(card?.priceUpdatedAt ?? card?.price_updated_at),
        source: toOptionalString(card?.source ?? card?.provider),
        provider: toOptionalString(card?.provider ?? card?.source),
        deltas: card?.deltas && typeof card.deltas === "object" ? card.deltas : null,
        priceHistory,
        price_history: priceHistory,
        historyPointCount: toOptionalNumber(card?.historyPointCount ?? card?.history_point_count),
        historyStartDate: toOptionalString(card?.historyStartDate ?? card?.history_start_date),
        historyEndDate: toOptionalString(card?.historyEndDate ?? card?.history_end_date),
        conditionIdUsed: toOptionalString(card?.conditionIdUsed ?? card?.condition_id_used),
        matchingConditionObservationCount: toOptionalNumber(
          card?.matchingConditionObservationCount ?? card?.matching_condition_observation_count
        ),
        historyDiagnostics:
          card?.historyDiagnostics && typeof card.historyDiagnostics === "object"
            ? card.historyDiagnostics
            : card?.history_diagnostics && typeof card.history_diagnostics === "object"
            ? card.history_diagnostics
            : null,
      };
    }),
    meta: payload?.meta || { sources: {}, warnings: [] },
  };
}

function normalizeSetValueHistoryPayload(payload) {
  const history = Array.isArray(payload?.history) ? payload.history : [];

  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug),
    },
    history: normalizeDailySetValueHistory(history),
    meta: payload?.meta || { sources: {}, warnings: [] },
  };
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
    throw requestError;
  }

  return payload;
}

export async function getPokemonSetTopMarketCards(setId, { limit = 10 } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const params = new URLSearchParams();
  if (limit) {
    params.set("limit", String(limit));
  }

  const response = await fetch(
    `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/top-cards${params.toString() ? `?${params}` : ""}`,
    {
      method: "GET",
      cache: "no-store",
    }
  );

  return normalizeTopMarketCardsPayload(
    await readJsonResponse(response, "Unable to load top market cards")
  );
}

export async function getPokemonSetValueHistory(setId, { days = 365 } = {}) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const params = new URLSearchParams();
  if (days) {
    params.set("days", String(days));
  }

  const response = await fetch(
    `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/market/value-history${params.toString() ? `?${params}` : ""}`,
    {
      method: "GET",
      cache: "no-store",
    }
  );

  return normalizeSetValueHistoryPayload(
    await readJsonResponse(response, "Unable to load set value history")
  );
}
