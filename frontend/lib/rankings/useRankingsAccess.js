"use client";

import { useAuth } from "@/components/AuthContext";
import { resolveRankingsPlanAccess } from "@/lib/access/indexPlanAccess.mjs";

export function resolveRankingsAccess(user) {
  return resolveRankingsPlanAccess(user);
}

export function useRankingsAccess() {
  const auth = useAuth();
  return resolveRankingsAccess(auth?.user);
}
