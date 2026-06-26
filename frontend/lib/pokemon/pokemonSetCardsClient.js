function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

const CARD_SNAPSHOT_TTL_MS = 24 * 60 * 60 * 1000;
const cardSnapshotCache = new Map();
const cardSnapshotInflight = new Map();
const isDev = process.env.NODE_ENV !== "production";
const RETRYABLE_SNAPSHOT_STATUSES = new Set([404, 500, 502, 503, 504]);

function nowMs() {
  return Date.now();
}

function debugTiming(label, details = {}) {
  if (!isDev) {
    return;
  }
  console.debug(`[pokemon-set-perf] ${label}`, details);
}

function getCardCacheKey(setId) {
  return `pokemon-set-cards:${String(setId || "").trim()}`;
}

function readCardCache(cacheKey, { allowStale = false } = {}) {
  const cached = cardSnapshotCache.get(cacheKey);
  if (!cached) {
    return null;
  }
  if (!allowStale && cached.expiresAt <= nowMs()) {
    return null;
  }
  return cached.payload;
}

function writeCardCache(cacheKey, payload) {
  cardSnapshotCache.set(cacheKey, {
    payload,
    cachedAt: nowMs(),
    expiresAt: nowMs() + CARD_SNAPSHOT_TTL_MS,
  });
}

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function isRetryableSnapshotError(error) {
  if (error?.retryable === true) {
    return true;
  }
  if (RETRYABLE_SNAPSHOT_STATUSES.has(Number(error?.status))) {
    return true;
  }
  const name = String(error?.name || "").toLowerCase();
  const message = String(error?.message || "").toLowerCase();
  return name === "typeerror" || message.includes("fetch failed") || message.includes("network");
}

function toOptionalNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toOptionalBoolean(value) {
  if (value === true || value === false) {
    return value;
  }
  const text = String(value ?? "").trim().toLowerCase();
  if (text === "true") return true;
  if (text === "false") return false;
  if (text === "1") return true;
  if (text === "0") return false;
  return Boolean(value);
}

function normalizeCardAppealMarketPriceCorrelation(payload) {
  const validationMeta = payload?.cardDesirabilityValidation?.meta || payload?.card_desirability_validation?.meta || {};
  const raw =
    payload?.cardAppealMarketPriceCorrelation ||
    payload?.card_appeal_market_price_correlation ||
    payload?.meta?.cardAppealMarketPriceCorrelation ||
    payload?.meta?.card_appeal_market_price_correlation ||
    validationMeta?.cardAppealMarketPriceCorrelation ||
    validationMeta?.card_appeal_market_price_correlation;
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const n = toOptionalNumber(raw.n ?? raw.included_count ?? raw.includedCount);
  const rawRows = Array.isArray(raw.plotRows)
    ? raw.plotRows
    : Array.isArray(raw.plot_rows)
    ? raw.plot_rows
    : Array.isArray(raw.rows)
    ? raw.rows
    : [];
  const rows = rawRows
    .map((row) => {
      const marketPrice = toOptionalNumber(row?.marketPrice ?? row?.market_price);
      const subjectDemandScore = toOptionalNumber(
        row?.subjectDesirabilityScore ??
          row?.subject_desirability_score ??
          row?.pokemonDesirabilityScore ??
          row?.pokemon_desirability_score
      );
      if (marketPrice === null || subjectDemandScore === null) {
        return null;
      }
      return {
        id: toOptionalString(row?.pokemonCanonicalCardId ?? row?.pokemon_canonical_card_id ?? row?.cardId ?? row?.card_id ?? row?.id),
        name: toOptionalString(row?.cardName ?? row?.card_name ?? row?.name) || "Unknown card",
        printedNumber: toOptionalString(row?.printedNumber ?? row?.printed_number),
        rarity: toOptionalString(row?.rarity),
        marketPrice,
        currentPrice: marketPrice,
        subjectDemandScore,
        pokemonDesirabilityScore: subjectDemandScore,
        cardDesirabilityScore: subjectDemandScore,
        treatmentScore: toOptionalNumber(row?.treatmentScore ?? row?.treatment_score),
        cardAppealScore: toOptionalNumber(row?.cardAppealScore ?? row?.card_appeal_score),
        adjustedCardAppealScore: toOptionalNumber(row?.adjustedCardAppealScore ?? row?.adjusted_card_appeal_score),
        isHitEligible: toOptionalBoolean(row?.isHitEligible ?? row?.is_hit_eligible),
        sampleSource: toOptionalString(row?.sampleSource ?? row?.sample_source),
      };
    })
    .filter(Boolean);
  return {
    canonicalCount: toOptionalNumber(raw.canonical_count ?? raw.canonicalCount),
    pricedCount: toOptionalNumber(raw.priced_count ?? raw.pricedCount),
    linkedCount: toOptionalNumber(raw.linked_count ?? raw.linkedCount),
    scoredLinkedCount: toOptionalNumber(raw.scored_linked_count ?? raw.scoredLinkedCount),
    includedCount: toOptionalNumber(raw.included_count ?? raw.includedCount),
    excludedUnpricedCount: toOptionalNumber(raw.excluded_unpriced_count ?? raw.excludedUnpricedCount),
    excludedUnlinkedCount: toOptionalNumber(raw.excluded_unlinked_count ?? raw.excludedUnlinkedCount),
    excludedMissingScoreCount: toOptionalNumber(raw.excluded_missing_score_count ?? raw.excludedMissingScoreCount),
    n,
    pearson: toOptionalNumber(raw.pearson),
    spearman: toOptionalNumber(raw.spearman),
    interpretation: toOptionalString(raw.interpretation),
    sampleSource: toOptionalString(raw.sample_source ?? raw.sampleSource),
    includedPolicy: toOptionalString(raw.included_policy ?? raw.includedPolicy),
    plottedCount: toOptionalNumber(raw.plotted_count ?? raw.plottedCount) ?? rows.length,
    rows,
    plotRows: rows,
  };
}

function normalizePayload(payload) {
  const cards = Array.isArray(payload?.cards) ? payload.cards : [];
  const validationRows = Array.isArray(payload?.cardDesirabilityValidation?.cards)
    ? payload.cardDesirabilityValidation.cards
    : Array.isArray(payload?.card_desirability_validation?.cards)
    ? payload.card_desirability_validation.cards
    : [];
  const validationByKey = new Map();
  validationRows.forEach((row) => {
    [
      toOptionalString(row?.cardId ?? row?.card_id),
      toOptionalString(row?.id),
      toOptionalString(row?.name),
    ].filter(Boolean).forEach((key) => {
      if (!validationByKey.has(key)) {
        validationByKey.set(key, row);
      }
    });
  });

  const cardAppealMarketPriceCorrelation = normalizeCardAppealMarketPriceCorrelation(payload);
  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug),
    },
    cards: cards.map((card) => {
      const validation =
        validationByKey.get(toOptionalString(card?.id)) ||
        validationByKey.get(toOptionalString(card?.cardId ?? card?.card_id)) ||
        validationByKey.get(toOptionalString(card?.name)) ||
        {};
      const currentPrice = toOptionalNumber(
        card?.currentPrice ??
          card?.current_price ??
          card?.marketPrice ??
          card?.market_price ??
          card?.estimated_market_price ??
          validation?.marketPrice ??
          validation?.market_price
      );
      const change30dAmount = toOptionalNumber(card?.change30dAmount ?? card?.change_30d_amount ?? card?.movement30d?.changeAmount ?? card?.movement30d?.change_amount);
      const change30dPercent = toOptionalNumber(card?.change30dPercent ?? card?.change_30d_percent ?? card?.movement30d?.changePercent ?? card?.movement30d?.change_percent);
      const movementScore = toOptionalNumber(card?.movementScore ?? card?.movement_score ?? card?.movement30d?.movementScore ?? card?.movement30d?.score);
      const movementLabel = toOptionalString(card?.movementLabel ?? card?.movement_label ?? card?.movement30d?.movementLabel ?? card?.movement30d?.label);
      const enoughHistory = Boolean(card?.enoughHistory ?? card?.enough_history ?? card?.movement30d?.enoughHistory ?? card?.movement30d?.enough_history);
      const subjectDemandScore = toOptionalNumber(card?.subjectDemandScore ?? card?.subject_demand_score ?? card?.pokemonDesirabilityScore ?? card?.pokemon_desirability_score ?? card?.cardDesirabilityScore ?? card?.card_desirability_score ?? validation?.pokemonDesirabilityScore ?? validation?.pokemon_desirability_score ?? validation?.cardDesirabilityScore ?? validation?.card_desirability_score);
      const treatmentScore = toOptionalNumber(card?.treatmentScore ?? card?.treatment_score ?? validation?.treatmentScore ?? validation?.treatment_score);
      const scarcityScore = toOptionalNumber(card?.scarcityScore ?? card?.scarcity_score ?? validation?.scarcityScore ?? validation?.scarcity_score);
      const adjustedCardAppealScore = toOptionalNumber(card?.adjustedCardAppealScore ?? card?.adjusted_card_appeal_score ?? validation?.adjustedCardAppealScore ?? validation?.adjusted_card_appeal_score);
      const cardAppealScore = toOptionalNumber(card?.cardAppealScore ?? card?.card_appeal_score ?? validation?.cardAppealScore ?? validation?.card_appeal_score) ?? adjustedCardAppealScore;

      return {
        id: toOptionalString(card?.id),
        name: toOptionalString(card?.name),
        setId: toOptionalString(card?.set_id ?? card?.setId),
        setName: toOptionalString(card?.set_name ?? card?.setName),
        pokemonTcgApiCardId: toOptionalString(card?.pokemon_tcg_api_card_id ?? card?.pokemonTcgApiCardId),
        cardNumber: toOptionalString(card?.card_number ?? card?.collector_number ?? card?.number),
        printedNumber: toOptionalString(card?.printed_number ?? card?.printedNumber),
        rarity: toOptionalString(card?.rarity),
        supertype: toOptionalString(card?.supertype),
        subtypes: Array.isArray(card?.subtypes) ? card.subtypes.map(toOptionalString).filter(Boolean) : [],
        nationalPokedexNumbers: Array.isArray(card?.national_pokedex_numbers ?? card?.nationalPokedexNumbers)
          ? (card?.national_pokedex_numbers ?? card?.nationalPokedexNumbers).map(toOptionalNumber).filter((value) => value !== null)
          : [],
        imageSmallUrl: toOptionalString(card?.image_small_url ?? card?.small_image_url),
        imageLargeUrl: toOptionalString(card?.image_large_url ?? card?.large_image_url),
        marketPrice: currentPrice ?? toOptionalNumber(card?.market_price ?? card?.estimated_market_price),
        currentPrice,
        cardVariantId: toOptionalString(card?.cardVariantId ?? card?.card_variant_id ?? validation?.cardVariantId ?? validation?.card_variant_id),
        subjectDemandScore,
        cardDesirabilityScore: subjectDemandScore,
        pokemonDesirabilityScore: subjectDemandScore,
        treatmentScore,
        scarcityScore,
        adjustedCardAppealScore,
        cardAppealScore,
        scarcityAdjustedCardAppealScore: toOptionalNumber(card?.scarcityAdjustedCardAppealScore ?? card?.scarcity_adjusted_card_appeal_score ?? validation?.scarcityAdjustedCardAppealScore ?? validation?.scarcity_adjusted_card_appeal_score),
        pullRate: toOptionalNumber(card?.pullRate ?? card?.pull_rate ?? validation?.pullRate ?? validation?.pull_rate),
        pullRateSource: toOptionalString(card?.pullRateSource ?? card?.pull_rate_source ?? validation?.pullRateSource ?? validation?.pull_rate_source),
        setValueShare: toOptionalNumber(card?.setValueShare ?? card?.set_value_share ?? validation?.setValueShare ?? validation?.set_value_share),
        linkedPokemonName: toOptionalString(card?.linkedPokemonName ?? card?.linked_pokemon_name ?? validation?.pokemonName ?? validation?.pokemon_name),
        linkedPokemon: Array.isArray(card?.linkedPokemon ?? card?.linked_pokemon)
          ? (card?.linkedPokemon ?? card?.linked_pokemon).map((entry) => ({
              pokemonName: toOptionalString(entry?.pokemonName ?? entry?.pokemon_name ?? entry?.name),
              pokemonReferenceId: toOptionalString(entry?.pokemonReferenceId ?? entry?.pokemon_reference_id),
              pokedexNumber: toOptionalNumber(entry?.pokedexNumber ?? entry?.pokedex_number),
              desirabilityScore: toOptionalNumber(entry?.desirabilityScore ?? entry?.desirability_score),
              contributionWeight: toOptionalNumber(entry?.contributionWeight ?? entry?.contribution_weight),
            })).filter((entry) => entry.pokemonName || entry.pokemonReferenceId)
          : [],
        isHitEligible: toOptionalBoolean(card?.isHitEligible ?? card?.is_hit_eligible ?? validation?.isHitEligible ?? validation?.is_hit_eligible),
        change30dAmount,
        change30dPercent,
        movementScore,
        movementLabel,
        enoughHistory,
        confidence: toOptionalString(card?.confidence ?? card?.movement30d?.confidence),
        movement30d: {
          currentPrice,
          changeAmount: change30dAmount,
          changePercent: change30dPercent,
          score: movementScore,
          label: movementLabel,
          enoughHistory,
          confidence: toOptionalString(card?.confidence ?? card?.movement30d?.confidence),
        },
        tcgplayerProductId: toOptionalString(card?.tcgplayer_product_id),
      };
    }),
    cardAppealMarketPriceCorrelation,
    meta: payload?.meta || { dedupe: {}, sources: {}, timings: {} },
  };
}

export async function getPokemonSetCards(setId) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    throw new Error("Set id is required");
  }

  const cacheKey = getCardCacheKey(resolvedSetId);
  const cached = readCardCache(cacheKey);
  if (cached) {
    debugTiming("cards.cache_hit", { setId: resolvedSetId });
    return cached;
  }
  if (cardSnapshotInflight.has(cacheKey)) {
    debugTiming("cards.inflight_join", { setId: resolvedSetId });
    return cardSnapshotInflight.get(cacheKey);
  }

  const startedAt = performance.now();
  debugTiming("cards.fetch_start", { setId: resolvedSetId });

  const request = (async () => {
    const url = `/api/tcgs/pokemon/sets/${encodeURIComponent(resolvedSetId)}/cards`;
    const staleCached = readCardCache(cacheKey, { allowStale: true });
    let payload = null;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const response = await fetch(url, {
          method: "GET",
        });

        try {
          payload = await response.json();
        } catch {
          payload = null;
        }

        if (!response.ok) {
          const message = payload?.message || payload?.error || "Unable to load set cards";
          const requestError = new Error(message);
          requestError.status = response.status;
          requestError.retryable = payload?.retryable === true;
          requestError.code = payload?.code;
          throw requestError;
        }
        break;
      } catch (error) {
        if (attempt > 0 || !isRetryableSnapshotError(error)) {
          if (staleCached) {
            debugTiming("cards.fetch_stale_cache_fallback", {
              setId: resolvedSetId,
              status: error?.status,
              error: error?.message || String(error),
            });
            return staleCached;
          }
          throw error;
        }
        debugTiming("cards.fetch_retry", {
          setId: resolvedSetId,
          status: error?.status,
          error: error?.message || String(error),
        });
        await wait(175);
      }
    }
    const normalized = normalizePayload(payload);
    writeCardCache(cacheKey, normalized);
    debugTiming("cards.fetch_success", {
      setId: resolvedSetId,
      elapsedMs: Math.round(performance.now() - startedAt),
      count: normalized.cards.length,
    });
    return normalized;
  })().finally(() => {
    cardSnapshotInflight.delete(cacheKey);
  });

  cardSnapshotInflight.set(cacheKey, request);
  return request;
}

export function getCachedPokemonSetCards(setId) {
  const resolvedSetId = String(setId || "").trim();
  return resolvedSetId ? readCardCache(getCardCacheKey(resolvedSetId)) : null;
}

export function prefetchPokemonSetCards(setId) {
  const resolvedSetId = String(setId || "").trim();
  if (!resolvedSetId) {
    return Promise.resolve(null);
  }
  return getPokemonSetCards(resolvedSetId).catch((error) => {
    debugTiming("cards.prefetch_error", {
      setId: resolvedSetId,
      error: error?.message || String(error),
    });
    return null;
  });
}
