import { normalizeIndexPlan } from "@/lib/access/indexPlanAccess.mjs";

// Pure branching logic for which plan-change mode a PaidCard should render.
// Deliberately extracted into its own dependency-free module (no JSX, no
// AuthContext/next imports) so it can be unit-tested without pulling in the
// component tree — see PricingPageClient.planChange.test.mjs.
export function resolvePaidCardMode(plan, status) {
  const effectivePlan = normalizeIndexPlan(status?.effectivePlan);
  const managed = Boolean(status?.billingManaged);

  if (effectivePlan === plan) {
    return "current";
  }
  if (!managed) {
    return "checkout";
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
