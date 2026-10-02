"use client";

import { useEffect, useState } from "react";
import { readRankingsScorecards } from "./rankingsScorecardsClient.mjs";
import { resolvePaidScorecards } from "./paidScorecardVisibility.mjs";

/**
 * Loads the ONE paid wide scorecard (all four benchmark metrics) for an entity
 * type, only while the viewer is entitled.  The sessionCache is scoped to the
 * access identity + publication, so a response can never be shared across an
 * access transition; the hook additionally drops anything that resolves after
 * entitlement was lost or the identity changed.
 */
export function usePaidScorecards(entityType, { sessionCache, entitled }) {
  const [state, setState] = useState(() => {
    const scorecards = entitled && sessionCache?.peek(`rankings:scorecards:${entityType}`);
    return scorecards?.status === "available" ? { identity: sessionCache.identity, status: "ready", scorecards } : { identity: sessionCache?.identity ?? null, status: "idle", scorecards: null };
  });
  useEffect(() => {
    if (!entitled || !sessionCache) {
      setState({ identity: null, status: "idle", scorecards: null });
      return undefined;
    }
    let live = true;
    const identity = sessionCache.identity;
    const cached = sessionCache.peek(`rankings:scorecards:${entityType}`);
    if (cached?.status === "available") {
      setState({ identity, status: "ready", scorecards: cached });
      return undefined;
    }
    setState((current) => (current.identity === identity && current.status === "ready" ? current : { identity, status: "loading", scorecards: null }));
    readRankingsScorecards(entityType, { sessionCache })
      .then((scorecards) => { if (live) setState({ identity, status: scorecards?.status === "available" ? "ready" : "error", scorecards: scorecards?.status === "available" ? scorecards : null }); })
      .catch(() => { if (live) setState({ identity, status: "error", scorecards: null }); });
    return () => { live = false; };
  }, [entityType, entitled, sessionCache]);
  return resolvePaidScorecards({ entitled, identity: sessionCache?.identity ?? null, state });
}
