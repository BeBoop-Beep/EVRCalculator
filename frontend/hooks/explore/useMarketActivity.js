"use client";

import { useEffect, useMemo, useState } from "react";
import { createActivityRequestOwner, ACTIVITY_STATUS, activityScopeKey } from "@/lib/explore/marketActivityState.mjs";

export default function useMarketActivity({ enabled, scope, transport, identityKey }) {
  const owner = useMemo(() => createActivityRequestOwner(transport || (() => Promise.reject(new Error("Activity transport unavailable.")))), [transport]);
  const [state, setState] = useState({ status: ACTIVITY_STATUS.idle, data: null, error: null, scopeKey: null });
  const scopeKey = activityScopeKey(scope);
  useEffect(() => {
    if (!enabled || !scopeKey || !identityKey) {
      owner.cancel();
      setState({ status: ACTIVITY_STATUS.idle, data: null, error: null, scopeKey: null });
      return owner.cancel;
    }
    setState((current) => ({ status: ACTIVITY_STATUS.loading, data: current.scopeKey === scopeKey ? current.data : null, error: null, scopeKey }));
    owner.request(scope).then((result) => {
      if (result.stale) return;
      setState(result.error
        ? { status: ACTIVITY_STATUS.error, data: null, error: result.error, scopeKey }
        : { status: ACTIVITY_STATUS.ready, data: result.data, error: null, scopeKey });
    });
    return owner.cancel;
  }, [enabled, scopeKey, identityKey, owner]);
  return state;
}

