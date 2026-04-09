// Profile data queries backed by backend API endpoints.
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
  const { method = "GET", body = undefined } = options;
  const response = await fetch(buildBackendUrl(path), {
    method,
    headers: await buildBackendHeaders(),
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
  const result = await fetchBackend("/profile/me");
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
 * @returns {Promise<ProfileDataResult<Pick<UserProfileRow, "id" | "username" | "display_name" | "avatar_url" | "bio" | "is_profile_public" | "location" | "favorite_tcg_id" | "created_at"> & { favorite_tcg_name: string | null; collection_summary: { portfolio_value: number | null; cards_count: number | null; sealed_count: number | null; graded_count: number | null; } | null; collection_summary_warning: string | null } | null>>}
 */
export async function getPublicProfileByUsername(usernameParam) {
  const username = normalizeUsernameForRoute(usernameParam);
  const result = await fetchBackend(`/profile/public/${encodeURIComponent(username)}`);
  if (result.error) {
    return { data: null, error: result.error };
  }

  return {
    data: result.data?.profile || null,
    error: null,
  };
}

/**
 * Returns selector options from public.tcgs ordered by name.
 * @returns {Promise<ProfileDataResult<TcgOption[]>>}
 */
export async function getTcgOptions() {
  const result = await fetchBackend("/profile/tcgs");
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
  });

  if (result.error) {
    return { data: null, error: result.error };
  }

  return {
    data: result.data?.profile || null,
    error: null,
  };
}
