// Profile data queries backed by backend API endpoints.
import "server-only";

import { headers } from "next/headers";
import { getAuthenticatedUserFromCookies } from "@/lib/authServer";
import { normalizeUsernameForRoute } from "@/lib/profile/publicIdentity";

/** @typedef {import("@/types/profile").UserProfileRow} UserProfileRow */
/** @typedef {import("@/types/profile").TcgOption} TcgOption */
/** @typedef {import("@/types/profile").ProfileUpdatePayload} ProfileUpdatePayload */
/** @typedef {import("@/types/profile").ProfileDataError} ProfileDataError */
/** @template T */
/** @typedef {import("@/types/profile").ProfileDataResult<T>} ProfileDataResult */

/** @param {string} message */
/** @param {number} status */
/** @param {string} [code] */
function createError(message, status, code) {
  return { message, status, code };
}

function getBackendBaseUrl() {
  return (process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

function buildBackendUrl(path) {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${getBackendBaseUrl()}${normalizedPath}`;
}

async function buildBackendHeaders() {
  const requestHeaders = {
    Accept: "application/json",
    "Content-Type": "application/json",
    "x-correlation-id": crypto.randomUUID(),
  };

  try {
    const incomingHeaders = await headers();
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

async function fetchBackend(path, options = {}) {
  const { method = "GET", body = undefined, traceLabel = "backend_request" } = options;
  const startedAt = Date.now();
  const requestHeaders = await buildBackendHeaders();
  const correlationId = requestHeaders["x-correlation-id"];

  console.info("[profile-backend-fetch] start", {
    traceLabel,
    path,
    method,
    correlationId,
  });

  const response = await fetch(buildBackendUrl(path), {
    method,
    headers: requestHeaders,
    credentials: "include",
    cache: "no-store",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  console.info("[profile-backend-fetch] end", {
    traceLabel,
    path,
    method,
    correlationId,
    status: response.status,
    ok: response.ok,
    elapsedMs: Date.now() - startedAt,
  });

  if (!response.ok) {
    return {
      data: null,
      error: createError(
        payload?.message || payload?.detail || `Request failed (${response.status})`,
        response.status,
        payload?.code
      ),
    };
  }

  return {
    data: payload,
    error: null,
  };
}

/** @returns {Promise<ProfileDataResult<{id: string; email?: string; name?: string} | null>>} */
async function getCurrentAuthenticatedUser() {
  const { user, error, status } = await getAuthenticatedUserFromCookies();

  if (!user || !user.id) {
    return { data: null, error: createError(error || "Not authenticated", status || 401, "AUTH_REQUIRED") };
  }

  return { data: user, error: null };
}

/** @param {string | number | null} favoriteTcgId */
/** @returns {Promise<ProfileDataResult<TcgOption | null>>} */
async function getFavoriteTcgById(favoriteTcgId) {
  const optionsResult = await getTcgOptions();
  if (optionsResult.error) {
    return {
      data: null,
      error: optionsResult.error,
    };
  }

  const match = (optionsResult.data || []).find((item) => String(item.id) === String(favoriteTcgId));
  return { data: match || null, error: null };
}

/**
 * Gets the currently authenticated user profile row and resolves favorite_tcg_id to favorite_tcg_name.
 * @returns {Promise<ProfileDataResult<UserProfileRow | null>>}
 */
export async function getCurrentAuthenticatedUserProfile() {
  const result = await fetchBackend("/profile/me", { traceLabel: "profile_me" });
  if (result.error) {
    return { data: null, error: result.error };
  }

  return {
    data: result.data?.profile || null,
    error: null,
  };
}

/**
 * Gets a public profile by route username.
 * Returns not found when profile is private.
 * @param {string} usernameParam
 * @returns {Promise<ProfileDataResult<Pick<UserProfileRow, "id" | "username" | "display_name" | "avatar_url" | "bio" | "is_profile_public" | "location" | "favorite_tcg_id" | "created_at"> & { favorite_tcg_name: string | null; collection_summary: { portfolio_value: number | null; cards_count: number | null; sealed_count: number | null; graded_count: number | null; portfolio_delta_1d: number | null; portfolio_delta_7d: number | null; portfolio_delta_3m: number | null; portfolio_delta_6m: number | null; portfolio_delta_1y: number | null; portfolio_delta_lifetime: number | null; portfolio_delta_pct_1d: number | null; portfolio_delta_pct_7d: number | null; portfolio_delta_pct_3m: number | null; portfolio_delta_pct_6m: number | null; portfolio_delta_pct_1y: number | null; portfolio_delta_pct_lifetime: number | null; } | null; collection_summary_warning: string | null } | null>>}
 */
export async function getPublicProfileByUsername(usernameParam) {
  const username = normalizeUsernameForRoute(usernameParam);
  const result = await fetchBackend(`/profile/public/${encodeURIComponent(username)}`, {
    traceLabel: "public_profile",
  });
  if (result.error) {
    return { data: null, error: result.error };
  }

  return {
    data: result.data?.profile || null,
    error: null,
  };
}

export async function getPublicCollectionByUsername(
  usernameParam,
  { includeCollectionItems = false, limit = null, offset = null } = {}
) {
  const username = normalizeUsernameForRoute(usernameParam);
  const searchParams = new URLSearchParams();
  if (includeCollectionItems) {
    searchParams.set("include_collection_items", "1");
  }
  if (Number.isFinite(Number(limit)) && Number(limit) > 0) {
    searchParams.set("limit", String(limit));
  }
  if (Number.isFinite(Number(offset)) && Number(offset) >= 0) {
    searchParams.set("offset", String(offset));
  }

  const suffix = searchParams.toString();
  const path = `/collection/items/public/${encodeURIComponent(username)}${suffix ? `?${suffix}` : ""}`;
  const result = await fetchBackend(path, {
    traceLabel: includeCollectionItems ? "public_collection_items" : "public_collection_summary",
  });

  if (result.error) {
    return { data: null, error: result.error };
  }

  return {
    data: result.data || null,
    error: null,
  };
}

/**
 * Returns selector options from public.tcgs ordered by name.
 * @returns {Promise<ProfileDataResult<TcgOption[]>>}
 */
export async function getTcgOptions() {
  const result = await fetchBackend("/profile/tcgs", { traceLabel: "profile_tcgs" });
  if (result.error) {
    return {
      data: [],
      error: result.error,
    };
  }

  return { data: result.data?.tcgs || [], error: null };
}

/**
 * Updates only editable profile columns for the currently authenticated user.
 * @param {ProfileUpdatePayload} payload
 * @returns {Promise<ProfileDataResult<UserProfileRow | null>>}
 */
export async function updateCurrentUserProfile(payload) {
  const authResult = await getCurrentAuthenticatedUser();
  if (authResult.error) {
    return { data: null, error: authResult.error };
  }

  const result = await fetchBackend("/profile/me", {
    method: "PUT",
    body: payload,
    traceLabel: "profile_me_update",
  });

  if (result.error) {
    return { data: null, error: result.error };
  }

  return {
    data: result.data?.profile || null,
    error: null,
  };
}
