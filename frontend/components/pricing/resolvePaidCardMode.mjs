import { normalizeIndexPlan } from "../../lib/access/indexPlanAccess.mjs";

// Pure branching logic for which plan-change mode a PaidCard should render.
// Deliberately extracted into its own dependency-free module (no JSX, no
// AuthContext/next imports) so it can be unit-tested without pulling in the
// component tree — see PricingPageClient.planChange.test.mjs.
export function resolvePaidCardMode(plan, status, offerKey = null) {
  const effectivePlan = normalizeIndexPlan(status?.effectivePlan);
  const managed = Boolean(status?.billingManaged);
  const currentOfferKey = status?.offerKey || null;

  // Current-plan display must never be affected by pending-state lookup
  // failures. When the current Stripe offer is known, only that exact
  // month/year card is current; the other interval becomes a change action.
  if (
    effectivePlan === plan &&
    (!offerKey || !currentOfferKey || offerKey === currentOfferKey)
  ) {
    return "current";
  }
  if (!managed) {
    return "checkout";
  }

  // A failed/unrecognized live pending-state lookup must never look
  // identical to a safe-to-take change action.
  if (status?.pendingChangeState === "unknown") {
    return "pending-unknown";
  }

  // Only one scheduled change can own a subscription schedule at a time.
  // The exact pending target lets the user cancel that change; every other
  // non-current offer stays blocked until the schedule is released.
  if (status?.pendingChangeState === "scheduled") {
    if (offerKey && status?.pendingOfferKey === offerKey) {
      return "pending-change";
    }
    return "pending-blocked";
  }

  if (effectivePlan === plan && offerKey && currentOfferKey && offerKey !== currentOfferKey) {
    return "interval-change";
  }
  if (plan === "plus" && effectivePlan === "premium") {
    return "downgrade";
  }
  if (plan === "premium" && effectivePlan === "plus") {
    return "upgrade";
  }
  return "checkout";
}
