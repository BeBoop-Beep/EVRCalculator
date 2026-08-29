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
  return resolveRankingsAccess(auth?.user);
}
