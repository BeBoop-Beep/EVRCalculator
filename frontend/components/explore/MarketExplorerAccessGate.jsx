// ---------------------------------------------------------------------------
// Market Explorer — the page-level entitlement boundary.
//
// WHAT CHANGED, AND WHY THIS FILE IS NOW ALMOST EMPTY. This used to be the
// single named place a future gate would be installed, because no entitlement
// architecture existed. One does now — `lib/access/indexPlanAccess.mjs`, the
// same authority Rankings reads — and installing it revealed that a PAGE-level
// gate is the wrong shape for this surface.
//
// MARKET EXPLORER IS NOT GATED AS A WHOLE, DELIBERATELY. The main Market page
// now carries a prominent CTA into this workspace; sending a visitor through it
// to a wall would make that CTA a bait. The Asset Market layer — Raw, Sealed,
// the chart, the timeframes — is the public market pulse and stays open to
// everyone. What varies by plan is DEPTH, and depth is gated where it lives:
// the rail groups (Index Plus) and Build a Market (Index Premium), both from
// the access object this page resolves server-side.
//
// So this component's remaining job is to STATE the boundary in the DOM. It
// reports the resolved access mode as a data attribute, which is what lets an
// end-to-end test assert what a given plan was actually served without
// reaching inside the workspace's internals.
//
// NOTHING HERE IS SECURITY. Every gate on this page is presentation. The API
// enforces Index Premium for custom market queries independently, server-side,
// from the profile row — see `_require_market_explorer_custom_markets`.
// ---------------------------------------------------------------------------

import { FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS } from "@/lib/access/indexPlanAccess.mjs";

/**
 * The plan this surface's DEEPEST capability requires.
 *
 * A feature identity, not a plan name: commercial packaging is not final, and
 * the tier a capability maps to must be changeable in one place.
 */
export const MARKET_EXPLORER_PREMIUM_FEATURE = FEATURE_MARKET_EXPLORER_CUSTOM_MARKETS;

export default function MarketExplorerAccessGate({ children, planAccess = null }) {
  // No `planAccess` means basic — the gate fails closed, though in practice
  // this only affects what the attribute reports, since the workspace resolves
  // access from its own `user` prop.
  const accessMode = planAccess?.accessMode || "basic";
  return (
    <div
      data-market-explorer-gate="open"
      data-market-explorer-access-mode={accessMode}
      data-market-explorer-premium-feature={MARKET_EXPLORER_PREMIUM_FEATURE}
      data-market-explorer-can-build-custom-markets={planAccess?.canBuildCustomMarkets ? "true" : "false"}
    >
      {children}
    </div>
  );
}
