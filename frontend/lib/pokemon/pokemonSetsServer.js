import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const BACKEND_URL = getBackendApiBaseUrl();

const SUCCESS_TTL_MS = 120_000;
const NOT_FOUND_TTL_MS = 10_000;

const setsCache = new Map();
const inflightRequests = new Map();

function toCacheKey() {
  return "pokemon-sets-catalog";
}

function toOptionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function toOptionalNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function normalisePayload(payload) {
  const sets = Array.isArray(payload?.sets) ? payload.sets : [];

  return {
    sets: sets.map((setSummary) => ({
      id: toOptionalString(setSummary?.id),
      name: toOptionalString(setSummary?.name),
      slug: toOptionalString(setSummary?.slug),
      era: toOptionalString(setSummary?.era),
      series: toOptionalString(setSummary?.series),
      releaseDate: toOptionalString(setSummary?.release_date ?? setSummary?.releaseDate),
      cardCount: toOptionalNumber(setSummary?.card_count ?? setSummary?.cardCount),
      setCode: toOptionalString(setSummary?.set_code ?? setSummary?.setCode),
      logoUrl: toOptionalString(setSummary?.logo_url ?? setSummary?.logoUrl),
      symbolUrl: toOptionalString(setSummary?.symbol_url ?? setSummary?.symbolUrl),
      imageUrl: toOptionalString(setSummary?.image_url ?? setSummary?.imageUrl),
    })),
    meta: payload?.meta || { warnings: [], timings: {}, sources: {} },
  };
}

const _fetchPokemonSets = cache(async function _fetchPokemonSets() {
  const cacheKey = toCacheKey();
  const now = Date.now();

  const cached = setsCache.get(cacheKey);
  if (cached && cached.expiresAt > now) {
    return cached.data;
  }

  if (inflightRequests.has(cacheKey)) {
    return inflightRequests.get(cacheKey);
  }

  const promise = (async () => {
    const url = `${BACKEND_URL}/tcgs/pokemon/sets`;
    const res = await fetch(url, { next: { revalidate: 900 } });

    if (res.status === 404) {
      const emptyPayload = normalisePayload(null);
      setsCache.set(cacheKey, {
        data: emptyPayload,
        expiresAt: now + NOT_FOUND_TTL_MS,
      });
      return emptyPayload;
    }

    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`Pokemon sets backend error ${res.status}: ${body}`);
    }

    const payload = normalisePayload(await res.json());
    setsCache.set(cacheKey, {
      data: payload,
      expiresAt: now + SUCCESS_TTL_MS,
    });
    return payload;
  })().finally(() => {
    inflightRequests.delete(cacheKey);
  });

  inflightRequests.set(cacheKey, promise);
  return promise;
});

export async function getPokemonSets() {
  return _fetchPokemonSets();
}
