import "server-only";
import { cache } from "react";

import { getPublicProfileIdentity } from "@/lib/profile/publicIdentity";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const PUBLIC_PROFILE_CACHE_TTL_MS = 120_000;
const PUBLIC_PROFILE_NOT_FOUND_TTL_MS = 10_000;

const publicProfileCache = new Map();
const publicProfileInflight = new Map();

function toCacheKey(usernameParam) {
  return String(usernameParam || "").trim().toLowerCase();
}

function getBackendBaseUrl() {
  return getBackendApiBaseUrl();
}

async function fetchPublicProfilePagePayloadFromBackend(username) {
  const response = await fetch(
    `${getBackendBaseUrl()}/public/profiles/${encodeURIComponent(username)}?include_collection_items=1`,
    {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      cache: "no-store",
    }
  );

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const error = new Error(payload?.message || payload?.detail || `Request failed (${response.status})`);
    error.status = response.status;
    error.code = payload?.code || "PUBLIC_PROFILE_PAGE_FETCH_FAILED";
    throw error;
  }

  return {
    profile: payload?.profile || null,
    collection_summary: payload?.collection_summary || null,
    collection_items: Array.isArray(payload?.collection_items) ? payload.collection_items : [],
    meta: payload?.meta || { warnings: [], timings: {} },
  };
}

const getPublicProfilePagePayloadPerRequest = cache(async function getPublicProfilePagePayloadPerRequest(usernameParam) {
  const username = String(usernameParam || "").trim();
  const cacheKey = toCacheKey(username);
  const startedAt = Date.now();

  const now = Date.now();
  const cachedEntry = publicProfileCache.get(cacheKey);
  if (cachedEntry && cachedEntry.expiresAt > now) {
    console.info("[public-profile-server] cache_hit", {
      username,
      cacheAgeMs: now - cachedEntry.cachedAt,
      ttlMs: cachedEntry.expiresAt - now,
    });
    return cachedEntry.data;
  }

  if (publicProfileInflight.has(cacheKey)) {
    console.info("[public-profile-server] inflight_reuse", {
      username,
    });
    return publicProfileInflight.get(cacheKey);
  }

  console.info("[public-profile-server] fetch_start", {
    username,
    cacheAction: "miss",
  });

  const fetchPromise = (async () => {
    try {
      const data = await fetchPublicProfilePagePayloadFromBackend(username);
      publicProfileCache.set(cacheKey, {
        data,
        cachedAt: Date.now(),
        expiresAt: Date.now() + PUBLIC_PROFILE_CACHE_TTL_MS,
      });

      console.info("[public-profile-server] fetch_success", {
        username,
        hasDisplayName: Boolean(data?.profile?.display_name),
        hasCollectionSummary: Boolean(data?.collection_summary),
        collectionItemCount: Array.isArray(data?.collection_items) ? data.collection_items.length : 0,
        warnings: data?.meta?.warnings || [],
        elapsedMs: Date.now() - startedAt,
        cacheAction: "store",
        ttlMs: PUBLIC_PROFILE_CACHE_TTL_MS,
      });

      return data;
    } catch (resultError) {
      const status = Number(resultError?.status || 0);
      console.warn("[public-profile-server] fetch_error", {
        username,
        status,
        code: resultError?.code || null,
        message: resultError?.message || "Request failed",
        elapsedMs: Date.now() - startedAt,
      });

      if (status === 404) {
        publicProfileCache.set(cacheKey, {
          data: null,
          cachedAt: Date.now(),
          expiresAt: Date.now() + PUBLIC_PROFILE_NOT_FOUND_TTL_MS,
        });
        return null;
      }

      const error = new Error(resultError?.message || "Public profile fetch failed");
      error.status = status || 500;
      error.code = resultError?.code || "PUBLIC_PROFILE_FETCH_FAILED";
      throw error;
    }
  })();

  publicProfileInflight.set(cacheKey, fetchPromise);

  try {
    return await fetchPromise;
  } finally {
    publicProfileInflight.delete(cacheKey);
  }
});

export async function getCachedPublicProfileByUsername(usernameParam) {
  const username = String(usernameParam || "").trim();
  const payload = await getPublicProfilePagePayloadPerRequest(username);
  if (!payload?.profile) {
    return null;
  }

  return {
    ...payload.profile,
    collection_summary: payload.collection_summary || null,
    collection_summary_warning:
      Array.isArray(payload?.meta?.warnings) && payload.meta.warnings.length > 0
        ? payload.meta.warnings.join("; ")
        : null,
  };
}

export async function getPublicProfilePagePayload(usernameParam) {
  const username = String(usernameParam || "").trim();
  return getPublicProfilePagePayloadPerRequest(username);
}

export async function getCachedPublicRouteContextByUsername(usernameParam) {
  const payload = await getPublicProfilePagePayload(usernameParam);
  const publicProfile = payload?.profile
    ? {
      ...payload.profile,
      collection_summary: payload.collection_summary || null,
      collection_summary_warning:
        Array.isArray(payload?.meta?.warnings) && payload.meta.warnings.length > 0
          ? payload.meta.warnings.join("; ")
          : null,
    }
    : null;
  const identity = getPublicProfileIdentity({
    ...publicProfile,
    username: publicProfile?.username || usernameParam,
  });

  return {
    payload,
    publicProfile,
    identity,
  };
}
