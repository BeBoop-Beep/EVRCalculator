import "server-only";
import { cache } from "react";

import { getPublicProfileByUsername } from "@/lib/profile/profileQueries";
import { getPublicProfileIdentity } from "@/lib/profile/publicIdentity";

const getPublicProfileByUsernamePerRequest = cache(async function getPublicProfileByUsernamePerRequest(usernameParam) {
  const username = String(usernameParam || "").trim();
  console.info("[public-profile-server] cache_bypass fetch_start", {
    username,
  });

  const result = await getPublicProfileByUsername(username);
  if (result.error) {
    const status = Number(result.error.status || 0);
    console.warn("[public-profile-server] cache_bypass fetch_error", {
      username,
      status,
      code: result.error.code || null,
      message: result.error.message || "Request failed",
      cacheAction: "skip_error_result",
    });

    if (status === 404) {
      return null;
    }

    const error = new Error(result.error.message || "Public profile fetch failed");
    error.status = status || 500;
    error.code = result.error.code || "PUBLIC_PROFILE_FETCH_FAILED";
    throw error;
  }

  console.info("[public-profile-server] cache_bypass fetch_success", {
    username,
    hasDisplayName: Boolean(result.data?.display_name),
    hasCollectionSummary: Boolean(result.data?.collection_summary),
    cacheAction: "bypass",
  });
  return result.data;
});

export async function getCachedPublicProfileByUsername(usernameParam) {
  const username = String(usernameParam || "").trim();
  return getPublicProfileByUsernamePerRequest(username);
}

export async function getCachedPublicRouteContextByUsername(usernameParam) {
  const publicProfile = await getCachedPublicProfileByUsername(usernameParam);
  const identity = getPublicProfileIdentity({
    ...publicProfile,
    username: publicProfile?.username || usernameParam,
  });

  return {
    publicProfile,
    identity,
  };
}
