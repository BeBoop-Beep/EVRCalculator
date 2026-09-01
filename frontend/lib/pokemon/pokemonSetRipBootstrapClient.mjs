import { normalizePokemonSetRipBootstrap } from "./pokemonSetRipBootstrapNormalizer.mjs";

const cache = new Map();
const MAX_ENTRIES = 6;
const TTL_MS = 5 * 60 * 1000;
const TIMEOUT_MS = 12_000;

const identity = (value) => String(value || "").trim();
const payloadSetId = (payload) => identity(payload?.set?.id || payload?.set?.target_id || payload?.set?.targetId);
const validForSet = (payload, setId) => Boolean(payload?.available && payloadSetId(payload) === identity(setId));
const trim = () => { while (cache.size > MAX_ENTRIES) cache.delete(cache.keys().next().value); };

export function seedPokemonSetRipBootstrap(setId, payload) {
  const id = identity(setId);
  if (!id || !validForSet(payload, id)) return null;
  cache.delete(id);
  cache.set(id, { storedAt: Date.now(), payload, promise: Promise.resolve(payload) });
  trim();
  return payload;
}

export function clearPokemonSetRipBootstrapCache(setId = null) {
  if (setId === null) cache.clear();
  else cache.delete(identity(setId));
}

export function getPokemonSetRipBootstrap(setId, { force = false } = {}) {
  const id = identity(setId);
  if (!id) return Promise.reject(new Error("Set RIP bootstrap identity is required"));
  if (force) cache.delete(id);
  const existing = cache.get(id);
  if (existing && Date.now() - existing.storedAt < TTL_MS) return existing.promise;
  if (existing) cache.delete(id);

  const controller = typeof AbortController === "function" ? new AbortController() : null;
  const timer = setTimeout(() => controller?.abort(), TIMEOUT_MS);
  const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost";
  const url = new URL(`/api/tcgs/pokemon/sets/${encodeURIComponent(id)}/rip/bootstrap`, origin);
  const promise = fetch(url, { cache: "no-store", headers: { Accept: "application/json" }, signal: controller?.signal })
    .then(async (response) => {
      if (!response.ok) throw new Error(`Set RIP bootstrap request failed (${response.status})`);
      const normalized = normalizePokemonSetRipBootstrap(await response.json());
      if (!validForSet(normalized, id)) throw new Error("Set RIP bootstrap response identity did not match the active set");
      const entry = cache.get(id);
      if (entry?.promise === promise) entry.payload = normalized;
      return normalized;
    })
    .catch((error) => {
      if (cache.get(id)?.promise === promise) cache.delete(id);
      if (error?.name === "AbortError") {
        const timeout = new Error("Set RIP bootstrap request timed out");
        timeout.code = "SET_RIP_BOOTSTRAP_TIMEOUT";
        throw timeout;
      }
      throw error;
    })
    .finally(() => clearTimeout(timer));
  cache.set(id, { storedAt: Date.now(), payload: null, promise });
  trim();
  return promise;
}

export const preloadPokemonSetRipBootstrap = getPokemonSetRipBootstrap;
export const SET_RIP_BOOTSTRAP_CACHE_LIMIT = MAX_ENTRIES;
export const SET_RIP_BOOTSTRAP_TTL_MS = TTL_MS;
