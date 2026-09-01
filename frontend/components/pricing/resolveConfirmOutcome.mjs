// Pure branching logic for how confirmPlanChangeAction should treat the
// confirm_plan_change response. Extracted into its own dependency-free
// module (mirrors resolvePaidCardMode.mjs) so it can be unit-tested without
// pulling in the component tree — see PricingPageClient.planChange.test.mjs.
//
// Per spec: downgrades have no paymentResult field at all (they are always
// "scheduled", never charged immediately) and must be treated as success.
// Upgrades carry paymentResult: "succeeded" | "requires_action" | "failed".
// Only "succeeded" (or the absent-field downgrade case) is a success; the
// other two must never be treated as Premium having been granted.
export function resolveConfirmOutcome(result) {
  const paymentResult = result?.paymentResult;
  if (paymentResult === undefined || paymentResult === "succeeded") {
    return { status: "success" };
  }
  if (paymentResult === "requires_action") {
    return { status: "requires_action" };
  }
  return { status: "failed" };
}
