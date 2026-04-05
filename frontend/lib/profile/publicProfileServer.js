import "server-only";

import { cache } from "react";
import { getPublicProfileByUsername } from "@/lib/profile/profileQueries";
import { getPublicProfileIdentity } from "@/lib/profile/publicIdentity";

export const getCachedPublicProfileByUsername = cache(async (usernameParam) => {
  const result = await getPublicProfileByUsername(usernameParam);
  if (result.error) return null;
  return result.data;
});

export const getCachedPublicRouteContextByUsername = cache(async (usernameParam) => {
  const publicProfile = await getCachedPublicProfileByUsername(usernameParam);
  const identity = getPublicProfileIdentity({
    ...publicProfile,
    username: publicProfile?.username || usernameParam,
  });

  return {
    publicProfile,
    identity,
  };
});
