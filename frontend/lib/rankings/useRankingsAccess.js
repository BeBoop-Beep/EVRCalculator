"use client";

import { useAuth } from "@/components/AuthContext";
import { resolveRankingsPlanAccess } from "@/lib/access/indexPlanAccess.mjs";

export function resolveRankingsAccess(user) {
  return resolveRankingsPlanAccess(user);
}

export function useRankingsAccess() {
  // Presentation only. Backend/Next projections must already have removed any
  // value this browser is not entitled to receive.
  const auth = useAuth();
  const access = resolveRankingsAccess(auth?.user);
  const identity = String(auth?.user?.id || auth?.user?.user_id || auth?.user?.email || "anonymous");
  return {
    ...access,
    authStatus: auth?.authStatus || "resolved",
    authRevision: auth?.authRevision || 0,
    requestKey: `${identity}:${access.accessMode}`,
  };
}
