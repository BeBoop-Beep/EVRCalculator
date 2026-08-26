"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import {
  buildEraSetTree,
  clearScope,
  toggleScopeEra,
  toggleScopeSet,
} from "@/lib/explore/marketExplorerScope.mjs";

// ---------------------------------------------------------------------------
// The Era & Sets scope, owned in one place.
//
// A scope is a NARROWING — "Scarlet & Violet", "Evolving Skies + Lost Origin" —
// and never a series. No backend publishes an era index, so selecting an era
// cannot put a line on the chart; filtering an already-aggregated global index
// in the browser would be a different number from a market built over that
// scope's own constituents.
//
// What a scope can do is be HANDED to the query engine, which builds that
// market for real. The hand-off is an explicit user action carrying a fresh
// token each time, so the two controls stay independent — Era & Sets never
// rewrites the builder underneath the user, and the builder never rewrites
// this.
// ---------------------------------------------------------------------------
const EMPTY_SCOPE = { eraIds: [], setIds: [] };

export default function useMarketExplorerScope(options, { asset = "cards" } = {}) {
  const [scope, setScope] = useState(EMPTY_SCOPE);
  const [handoff, setHandoff] = useState(null);
  // A monotonic counter, NOT a timestamp. Nothing on this page may derive
  // anything from the clock: a value that differs between the server render and
  // the client render is a hydration mismatch waiting to happen.
  const pressCount = useRef(0);

  const tree = useMemo(
    () => buildEraSetTree(options, { asset, eraIds: scope.eraIds, setIds: scope.setIds }),
    [options, asset, scope]
  );

  const toggleEra = useCallback(
    (eraId) => setScope((current) => toggleScopeEra(current, eraId, tree)),
    [tree]
  );
  const toggleSet = useCallback(
    (setId) => setScope((current) => toggleScopeSet(current, setId, tree)),
    [tree]
  );
  const reset = useCallback(() => setScope(clearScope()), []);
  const handOffToBuilder = useCallback(() => {
    // A new token per press, so asking twice re-applies rather than being
    // swallowed as an unchanged value.
    pressCount.current += 1;
    setHandoff({ eraIds: scope.eraIds, setIds: scope.setIds, token: pressCount.current });
  }, [scope]);

  return { scope, tree, handoff, toggleEra, toggleSet, reset, handOffToBuilder };
}
