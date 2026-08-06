"use client";

// Owns ONE RIP metric section's disclosure state.
//
// This is deliberately a separate module from RipMetricDisclosureRow.jsx. The
// row is pure presentation and has no viewport dependency at all, so keeping
// the media query out of its module lets the row be rendered and asserted on
// directly. Everything viewport-shaped lives here, and the actual open-set
// decision lives in ripDisclosurePolicy.mjs, where it can be tested as the
// decision it is.
//
// Each section calls this hook separately. That is what makes Financial RIP's
// and Collector Appeal's accordions independent: two hooks, two open-sets, so
// expanding a factor in one never collapses a component in the other.

import { useCallback, useMemo, useState } from "react";

import useMediaQuery from "@/hooks/useMediaQuery";
import { resolveNextOpenKeys } from "./ripDisclosurePolicy.mjs";

// The same `desk` breakpoint the rest of the set page treats as desktop, read
// through the existing shared hook rather than through a second viewport
// implementation of its own.
export const RIP_DISCLOSURE_DESKTOP_QUERY = "(min-width: 1200px)";

export default function useRipDisclosureSection() {
  // SSR and the first client paint assume DESKTOP, matching useMediaQuery's
  // documented contract, so hydration can never momentarily apply the narrower
  // single-open policy to a desktop reader.
  const isDesktop = useMediaQuery(RIP_DISCLOSURE_DESKTOP_QUERY, true);
  const [openKeys, setOpenKeys] = useState(() => []);

  const toggle = useCallback(
    (key) => {
      setOpenKeys((previous) => resolveNextOpenKeys(previous, key, { isDesktop }));
    },
    [isDesktop]
  );

  // Narrowing a desktop window does not retroactively collapse rows: discarding
  // a reader's expanded state underneath them would be worse than briefly
  // showing two open panels. The policy applies at the next toggle.
  return useMemo(() => ({ isDesktop, openKeys, toggle }), [isDesktop, openKeys, toggle]);
}
