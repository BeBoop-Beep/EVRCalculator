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

function readCardCache(cacheKey) {
  const cached = cardSnapshotCache.get(cacheKey);
  if (!cached || cached.expiresAt <= nowMs()) {
    if (cached) {
      cardSnapshotCache.delete(cacheKey);
    }
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
  return RETRYABLE_SNAPSHOT_STATUSES.has(Number(error?.status));
}

function toOptionalNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizePayload(payload) {
  const cards = Array.isArray(payload?.cards) ? payload.cards : [];

  return {
    set: {
      id: toOptionalString(payload?.set?.id),
      name: toOptionalString(payload?.set?.name),
      slug: toOptionalString(payload?.set?.slug),
    },
    cards: cards.map((card) => {
      const currentPrice = toOptionalNumber(card?.currentPrice ?? card?.current_price ?? card?.marketPrice ?? card?.market_price ?? card?.estimated_market_price);
      const change30dAmount = toOptionalNumber(card?.change30dAmount ?? card?.change_30d_amount ?? card?.movement30d?.changeAmount ?? card?.movement30d?.change_amount);
      const change30dPercent = toOptionalNumber(card?.change30dPercent ?? card?.change_30d_percent ?? card?.movement30d?.changePercent ?? card?.movement30d?.change_percent);
      const movementScore = toOptionalNumber(card?.movementScore ?? card?.movement_score ?? card?.movement30d?.movementScore ?? card?.movement30d?.score);
      const movementLabel = toOptionalString(card?.movementLabel ?? card?.movement_label ?? card?.movement30d?.movementLabel ?? card?.movement30d?.label);
      const enoughHistory = Boolean(card?.enoughHistory ?? card?.enough_history ?? card?.movement30d?.enoughHistory ?? card?.movement30d?.enough_history);

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
          throw requestError;
        }
        break;
      } catch (error) {
        if (attempt > 0 || !isRetryableSnapshotError(error)) {
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
