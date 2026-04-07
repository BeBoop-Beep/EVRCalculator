// Profile data queries; delegates collection summary fetching to publicCollectionSummaryAccessor.
import { createSupabaseAdminClient } from "@/lib/supabaseServer";
import { getAuthenticatedUserFromCookies } from "@/lib/authServer";
import { normalizeUsernameForRoute } from "@/lib/profile/publicIdentity";
import { getPublicCollectionSummaryByUsername } from "@/lib/profile/publicCollectionSummaryAccessor";

const PROFILE_SELECT_FIELDS = [
  "id",
  "email",
  "username",
  "display_name",
  "bio",
  "avatar_url",
  "location",
  "favorite_tcg_id",
  "is_profile_public",
  "show_portfolio_value",
  "show_activity",
  "created_at",
  "updated_at",
].join(", ");

const EDITABLE_PROFILE_FIELDS = new Set([
  "display_name",
  "bio",
  "location",
  "favorite_tcg_id",
  "is_profile_public",
  "show_portfolio_value",
  "show_activity",
]);

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

/** @param {unknown} value */
function normalizeFavoriteTcgId(value) {
  if (value === undefined || value === null || value === "") {
    return null;
  }

  if (typeof value === "number" || typeof value === "string") {
    return value;
  }

  return undefined;
}

/** @param {unknown} value */
function asTrimmedNullableString(value) {
  if (value === undefined) return undefined;
  if (value === null) return null;
  if (typeof value !== "string") return undefined;

  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
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
  if (!favoriteTcgId) {
    return { data: null, error: null };
  }

  const adminClient = createSupabaseAdminClient();
  const { data, error } = await adminClient
    .from("tcgs")
    .select("id, name")
    .eq("id", favoriteTcgId)
    .maybeSingle();

  if (error) {
    return {
      data: null,
      error: createError("Unable to resolve favorite TCG", 500, error.code),
    };
  }

  return { data: data || null, error: null };
}

/**
 * Gets the currently authenticated user profile row and resolves favorite_tcg_id to favorite_tcg_name.
 * @returns {Promise<ProfileDataResult<UserProfileRow | null>>}
 */
export async function getCurrentAuthenticatedUserProfile() {
  const authResult = await getCurrentAuthenticatedUser();

  if (authResult.error || !authResult.data?.id) {
    return { data: null, error: authResult.error || createError("Not authenticated", 401, "AUTH_REQUIRED") };
  }

  const adminClient = createSupabaseAdminClient();
  const { data: profile, error } = await adminClient
    .from("users")
    .select(PROFILE_SELECT_FIELDS)
    .eq("id", authResult.data.id)
    .maybeSingle();

  if (error) {
    return {
      data: null,
      error: createError("Unable to fetch profile", 500, error.code),
    };
  }

  if (!profile) {
    return {
      data: null,
      error: createError("Profile not found", 404, "PROFILE_NOT_FOUND"),
    };
  }

  const favoriteTcgResult = await getFavoriteTcgById(profile.favorite_tcg_id);

  if (favoriteTcgResult.error) {
    return { data: null, error: favoriteTcgResult.error };
  }

  return {
    data: {
      ...profile,
      favorite_tcg_name: favoriteTcgResult.data?.name || null,
    },
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

  const adminClient = createSupabaseAdminClient();
  const { data: profile, error } = await adminClient
    .from("users")
    .select("id, username, display_name, avatar_url, bio, is_profile_public, location, favorite_tcg_id, created_at")
    .eq("username", username)
    .maybeSingle();

  if (error) {
    return {
      data: null,
      error: createError("Unable to fetch public profile", 500, error.code),
    };
  }

  if (!profile) {
    return {
      data: null,
      error: createError("Public profile not found", 404, "PROFILE_NOT_FOUND"),
    };
  }

  if (profile.is_profile_public === false) {
    const authResult = await getCurrentAuthenticatedUser();
    const isOwner = !authResult.error && authResult.data?.id && authResult.data.id === profile.id;

    if (!isOwner) {
      return {
        data: null,
        error: createError("Public profile not found", 404, "PROFILE_NOT_FOUND"),
      };
    }
  }

  // Resolve favorite TCG name if available
  let favorite_tcg_name = null;
  if (profile.favorite_tcg_id) {
    const favoriteTcgResult = await getFavoriteTcgById(profile.favorite_tcg_id);
    favorite_tcg_name = favoriteTcgResult.data?.name || null;
  }

  const summaryResult = await getPublicCollectionSummaryByUsername(profile.username || username);

  return {
    data: {
      ...profile,
      favorite_tcg_name,
      collection_summary: summaryResult.data,
      collection_summary_warning: summaryResult.warning,
    },
    error: null,
  };
}

/**
 * Returns selector options from public.tcgs ordered by name.
 * @returns {Promise<ProfileDataResult<TcgOption[]>>}
 */
export async function getTcgOptions() {
  const adminClient = createSupabaseAdminClient();
  const { data, error } = await adminClient
    .from("tcgs")
    .select("id, name")
    .order("name", { ascending: true });

  if (error) {
    return {
      data: [],
      error: createError("Unable to fetch TCG options", 500, error.code),
    };
  }

  return { data: data || [], error: null };
}

/**
 * Updates only editable profile columns for the currently authenticated user.
 * @param {ProfileUpdatePayload} payload
 * @returns {Promise<ProfileDataResult<UserProfileRow | null>>}
 */
export async function updateCurrentUserProfile(payload) {
  const authResult = await getCurrentAuthenticatedUser();

  if (authResult.error || !authResult.data?.id) {
    return { data: null, error: authResult.error || createError("Not authenticated", 401, "AUTH_REQUIRED") };
  }

  if (!payload || typeof payload !== "object") {
    return {
      data: null,
      error: createError("Invalid update payload", 400, "INVALID_PAYLOAD"),
    };
  }

  const incomingKeys = Object.keys(payload);
  if (incomingKeys.length === 0) {
    return {
      data: null,
      error: createError("No fields provided for update", 400, "EMPTY_PAYLOAD"),
    };
  }

  for (const key of incomingKeys) {
    if (!EDITABLE_PROFILE_FIELDS.has(key)) {
      return {
        data: null,
        error: createError(`Unsupported field: ${key}`, 400, "UNSUPPORTED_FIELD"),
      };
    }
  }

  const normalizedFavoriteTcgId = normalizeFavoriteTcgId(payload.favorite_tcg_id);
  if (normalizedFavoriteTcgId === undefined) {
    return {
      data: null,
      error: createError("favorite_tcg_id must be string, number, null, or empty string", 400, "INVALID_FAVORITE_TCG_ID"),
    };
  }

  if (normalizedFavoriteTcgId !== null && payload.favorite_tcg_id !== undefined) {
    const favoriteTcgResult = await getFavoriteTcgById(normalizedFavoriteTcgId);
    if (favoriteTcgResult.error || !favoriteTcgResult.data) {
      return {
        data: null,
        error: createError("Selected favorite TCG does not exist", 400, "INVALID_FAVORITE_TCG"),
      };
    }
  }

  const nextPayload = {};

  if (payload.display_name !== undefined) {
    const value = asTrimmedNullableString(payload.display_name);
    if (value === undefined) {
      return { data: null, error: createError("display_name must be a string or null", 400, "INVALID_DISPLAY_NAME") };
    }
    nextPayload.display_name = value;
  }

  if (payload.bio !== undefined) {
    const value = asTrimmedNullableString(payload.bio);
    if (value === undefined) {
      return { data: null, error: createError("bio must be a string or null", 400, "INVALID_BIO") };
    }
    nextPayload.bio = value;
  }

  if (payload.location !== undefined) {
    const value = asTrimmedNullableString(payload.location);
    if (value === undefined) {
      return { data: null, error: createError("location must be a string or null", 400, "INVALID_LOCATION") };
    }
    nextPayload.location = value;
  }

  if (payload.favorite_tcg_id !== undefined) {
    nextPayload.favorite_tcg_id = normalizedFavoriteTcgId;
  }

  if (payload.is_profile_public !== undefined) {
    if (typeof payload.is_profile_public !== "boolean") {
      return { data: null, error: createError("is_profile_public must be a boolean", 400, "INVALID_IS_PROFILE_PUBLIC") };
    }
    nextPayload.is_profile_public = payload.is_profile_public;
  }

  if (payload.show_portfolio_value !== undefined) {
    if (typeof payload.show_portfolio_value !== "boolean") {
      return { data: null, error: createError("show_portfolio_value must be a boolean", 400, "INVALID_SHOW_PORTFOLIO_VALUE") };
    }
    nextPayload.show_portfolio_value = payload.show_portfolio_value;
  }

  if (payload.show_activity !== undefined) {
    if (typeof payload.show_activity !== "boolean") {
      return { data: null, error: createError("show_activity must be a boolean", 400, "INVALID_SHOW_ACTIVITY") };
    }
    nextPayload.show_activity = payload.show_activity;
  }

  nextPayload.updated_at = new Date().toISOString();

  const adminClient = createSupabaseAdminClient();
  const { data: updatedProfile, error } = await adminClient
    .from("users")
    .update(nextPayload)
    .eq("id", authResult.data.id)
    .select(PROFILE_SELECT_FIELDS)
    .maybeSingle();

  if (error) {
    return {
      data: null,
      error: createError("Unable to update profile", 500, error.code),
    };
  }

  if (!updatedProfile) {
    return {
      data: null,
      error: createError("Profile not found", 404, "PROFILE_NOT_FOUND"),
    };
  }

  const favoriteTcgResult = await getFavoriteTcgById(updatedProfile.favorite_tcg_id);
  if (favoriteTcgResult.error) {
    return { data: null, error: favoriteTcgResult.error };
  }

  return {
    data: {
      ...updatedProfile,
      favorite_tcg_name: favoriteTcgResult.data?.name || null,
    },
    error: null,
  };
}
