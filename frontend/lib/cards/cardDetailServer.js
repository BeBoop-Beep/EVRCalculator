import "server-only";
import { cache } from "react";

import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const BACKEND_URL = getBackendApiBaseUrl();
const SUCCESS_TTL_MS = 120_000;
const NOT_FOUND_TTL_MS = 10_000;

const cardDetailCache = new Map();
const inflightRequests = new Map();

function toCacheKey(cardVariantId) {
  return `card-detail:${String(cardVariantId || "").trim()}`;
}

function normalizePayload(payload) {
  return {
    identity: payload?.identity || null,
    images: payload?.images || {
      image_small_url: null,
      image_large_url: null,
      image_source: "fallback",
      fallback_used: true,
    },
    set: payload?.set || null,
    variant_options: Array.isArray(payload?.variant_options) ? payload.variant_options : [],
    condition_prices: Array.isArray(payload?.condition_prices) ? payload.condition_prices : [],
    graded_prices: Array.isArray(payload?.graded_prices) ? payload.graded_prices : [],
    price_history: {
      raw: Array.isArray(payload?.price_history?.raw) ? payload.price_history.raw : [],
      graded: Array.isArray(payload?.price_history?.graded) ? payload.price_history.graded : [],
    },
    simulation_context: payload?.simulation_context || null,
    user_inventory_state: payload?.user_inventory_state || {
      is_authenticated: false,
      card_holdings: [],
      graded_holdings: [],
    },
    meta: payload?.meta || { warnings: [], timings: {}, sources: {} },
  };
}

async function buildBackendHeaders() {
  const requestHeaders = {
    Accept: "application/json",
  };

  try {
    const mod = await import("next/headers");
    const incomingHeaders = await mod.headers();
    const cookieHeader = incomingHeaders.get("cookie");
    const authorizationHeader = incomingHeaders.get("authorization");

    if (cookieHeader) {
      requestHeaders.cookie = cookieHeader;
    }

    if (authorizationHeader) {
      requestHeaders.authorization = authorizationHeader;
    }
  } catch {
    // Ignore header extraction failures in non-request contexts.
  }

  return requestHeaders;
}

const _fetchCardDetailPagePayload = cache(async function _fetchCardDetailPagePayload(cardVariantId) {
  const cacheKey = toCacheKey(cardVariantId);
  const now = Date.now();

  const cached = cardDetailCache.get(cacheKey);
  if (cached && cached.expiresAt > now) {
    return cached.data;
  }

  if (inflightRequests.has(cacheKey)) {
    return inflightRequests.get(cacheKey);
  }

  const promise = (async () => {
    const response = await fetch(
      `${BACKEND_URL}/cards/${encodeURIComponent(String(cardVariantId))}/page`,
      {
        method: "GET",
        headers: await buildBackendHeaders(),
        credentials: "include",
        cache: "no-store",
      }
    );

    if (response.status === 404) {
      cardDetailCache.set(cacheKey, {
        data: null,
        expiresAt: now + NOT_FOUND_TTL_MS,
      });
      return null;
    }

    let payload = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }

    if (!response.ok) {
      const error = new Error(payload?.message || `Card detail backend error ${response.status}`);
      error.status = response.status;
      error.code = payload?.code || "CARD_DETAIL_FETCH_FAILED";
      throw error;
    }

    const normalized = normalizePayload(payload);
    cardDetailCache.set(cacheKey, {
      data: normalized,
      expiresAt: now + SUCCESS_TTL_MS,
    });
    return normalized;
  })().finally(() => {
    inflightRequests.delete(cacheKey);
  });

  inflightRequests.set(cacheKey, promise);
  return promise;
});

export async function getCardDetailPagePayload(cardVariantIdParam) {
  const cardVariantId = String(cardVariantIdParam || "").trim();
  if (!cardVariantId) {
    return null;
  }

  return _fetchCardDetailPagePayload(cardVariantId);
}
