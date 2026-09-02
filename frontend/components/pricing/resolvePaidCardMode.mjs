import { normalizeIndexPlan } from "@/lib/access/indexPlanAccess.mjs";

// Pure branching logic for which plan-change mode a PaidCard should render.
// Deliberately extracted into its own dependency-free module (no JSX, no
// AuthContext/next imports) so it can be unit-tested without pulling in the
// component tree — see PricingPageClient.planChange.test.mjs.
export function resolvePaidCardMode(plan, status) {
  const effectivePlan = normalizeIndexPlan(status?.effectivePlan);
  const managed = Boolean(status?.billingManaged);

  // Current-plan display must never be affected by pending-state lookup
  // failures -- effective entitlement stays local/reconciliation-driven
  // regardless of whether the live Stripe enrichment succeeded.
  if (effectivePlan === plan) {
    return "current";
  }
  if (!managed) {
    return "checkout";
  }

  // A failed/unrecognized live pending-state lookup must never look
  // identical to "no pending change" (mode "downgrade"/"upgrade" imply the
  // action is safe to take right now) -- disable the action and let the UI
  // show a restrained "can't verify" message instead.
  if (status?.pendingChangeState === "unknown") {
    return "pending-unknown";
  }

  if (plan === "plus" && effectivePlan === "premium") {
    if (status?.pendingChangeState === "scheduled" && status?.pendingPlan === "plus") {
      return "pending-downgrade";
    }
    return "downgrade";
  }
  if (plan === "premium" && effectivePlan === "plus") {
    return "upgrade";
  }
  return "checkout";
}
