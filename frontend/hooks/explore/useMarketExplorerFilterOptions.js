"use client";

import { useEffect, useState } from "react";

// ---------------------------------------------------------------------------
// ONE canonical filter-options request for the whole workspace.
//
// Era & Sets navigation and Build a Market read the SAME authority — eras,
// sets, card rarities and sealed families all come from
// /api/market/explorer/query. Two components fetching it independently would
// double the request and, worse, could render two different era lists if one
// resolved against a stale cache. This module-level cache makes the payload a
// single fact for the page.
//
// EXPANDING A GROUP MUST NOT QUERY A MARKET. This fetches the OPTION LIST only,
// once, on mount. Opening or closing a disclosure is pure client state and
// issues no request at all.
// ---------------------------------------------------------------------------

/** The distinguishable outcomes of loading the canonical filters. */
export const OPTIONS_STATUS = {
  loading: "loading",
  ready: "ready",
  signedOut: "signedOut",
  unavailable: "unavailable",
  offline: "offline",
};

/** Map an HTTP status onto the state the user can actually act on. */
export function resolveOptionsStatus(httpStatus) {
  if (httpStatus === 401 || httpStatus === 403) return OPTIONS_STATUS.signedOut;
  return OPTIONS_STATUS.unavailable;
}

/** FastAPI answers with `detail`; the app's own routes answer with `message`. */
export function backendMessage(payload) {
  if (!payload || typeof payload !== "object") return "";
  const detail = typeof payload.detail === "string" ? payload.detail : "";
  return String(payload.message || detail || "");
}

let inFlight = null;
let cached = null;

async function loadOptions() {
  if (cached) return cached;
  if (!inFlight) {
    inFlight = (async () => {
      try {
        const response = await fetch("/api/market/explorer/query", { credentials: "include" });
        const payload = await response.json().catch(() => null);
        const result = response.ok
          ? { status: OPTIONS_STATUS.ready, options: payload, message: "" }
          : { status: resolveOptionsStatus(response.status), options: null, message: backendMessage(payload) };
        // Only a SUCCESS is cached. A signed-out or failed answer must be
        // retried by the next mount — the user may have signed in since.
        if (result.status === OPTIONS_STATUS.ready) cached = result;
        return result;
      } catch {
        // A thrown fetch is a transport failure, never an auth answer.
        return { status: OPTIONS_STATUS.offline, options: null, message: "" };
      } finally {
        inFlight = null;
      }
    })();
  }
  return inFlight;
}

/** Reset the module cache. Tests only — production never re-authenticates. */
export function __resetMarketExplorerFilterOptionsCache() {
  cached = null;
  inFlight = null;
}

export default function useMarketExplorerFilterOptions() {
  const [state, setState] = useState(() => cached || { status: OPTIONS_STATUS.loading, options: null, message: "" });

  useEffect(() => {
    if (state.status === OPTIONS_STATUS.ready) return undefined;
    let live = true;
    loadOptions().then((result) => { if (live) setState(result); });
    return () => { live = false; };
    // Intentionally mount-only: the option list is canonical, not reactive.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return state;
}
