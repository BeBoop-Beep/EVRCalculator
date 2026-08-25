// ---------------------------------------------------------------------------
// Market Explorer — entitlement boundary.
//
// Market Explorer is intended to become an Index Plus (paid) research feature.
// THIS BRANCH HAS NO SUBSCRIPTION/ENTITLEMENT ARCHITECTURE — there is no
// entitlement provider, no plan claim on the session, and no existing gated
// component anywhere in the app to reuse.
//
// So this file deliberately does exactly one thing: it is the single, named
// place the real gate will be installed, and until then it renders its children
// unchanged. It does NOT invent a second authentication system, and it does NOT
// hardcode a fake entitlement value — a locally-invented `isPaid` flag would be
// a security-shaped lie that some later component would start trusting.
//
// WHEN THE GATE SHIPS, the only change here is to read the real entitlement and
// branch: `preview` (title, the three parent-market cards and their headline
// values — enough to understand the value proposition) for unentitled users,
// `children` (chart, timeframes, filters, detail strip) for entitled ones. The
// page already passes both, so no caller changes.
// ---------------------------------------------------------------------------

/** The plan this surface will require. Referenced, not enforced, in Phase 1. */
export const MARKET_EXPLORER_REQUIRED_PLAN = "index-plus";

export default function MarketExplorerAccessGate({ children, preview = null }) {
  // No entitlement source exists yet, so there is nothing to evaluate and the
  // workspace is open. `preview` is accepted and intentionally unused until it
  // is: the shape is proven at the call site now so installing the gate is a
  // one-line change here rather than a page rewrite.
  void preview;
  return (
    <div data-market-explorer-gate="open" data-market-explorer-required-plan={MARKET_EXPLORER_REQUIRED_PLAN}>
      {children}
    </div>
  );
}
