"use client";

import { useAuth } from "@/components/AuthContext";

export function resolveRankingsAccess(user) {
  return {
    canViewRankingsIntelligence: Boolean(user),
    accessMode: user ? "authenticated-preview" : "free",
  };
}

export function useRankingsAccess() {
  const auth = useAuth();
  // TEMPORARY PRE-LAUNCH ACCESS: Authenticated users receive Rankings intelligence until the real
  // Index Plus entitlement/billing gate is available. Replace this auth check with the canonical
  // Index Plus entitlement; do not extend this temporary rule to other premium features automatically.
  return resolveRankingsAccess(auth?.user);
}
