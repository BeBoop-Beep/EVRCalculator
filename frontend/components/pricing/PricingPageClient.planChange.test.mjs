import assert from "node:assert/strict";
import { test } from "node:test";

import { resolvePaidCardMode } from "./resolvePaidCardMode.mjs";
import { resolveConfirmOutcome } from "./resolveConfirmOutcome.mjs";

test("basic user sees checkout for both plus and premium", () => {
  const status = { effectivePlan: null, billingManaged: false, pendingChangeState: "none" };
  assert.equal(resolvePaidCardMode("plus", status, "plus_annual"), "checkout");
  assert.equal(resolvePaidCardMode("premium", status, "premium_annual"), "checkout");
});

test("plus monthly user sees current monthly plus and interval change on annual plus", () => {
  const status = {
    effectivePlan: "plus",
    billingManaged: true,
    offerKey: "plus_monthly",
    pendingChangeState: "none",
  };
  assert.equal(resolvePaidCardMode("plus", status, "plus_monthly"), "current");
  assert.equal(resolvePaidCardMode("plus", status, "plus_annual"), "interval-change");
  assert.equal(resolvePaidCardMode("premium", status, "premium_monthly"), "upgrade");
});

test("plus annual user can change back to monthly at period end", () => {
  const status = {
    effectivePlan: "plus",
    billingManaged: true,
    offerKey: "plus_annual",
    pendingChangeState: "none",
  };
  assert.equal(resolvePaidCardMode("plus", status, "plus_annual"), "current");
  assert.equal(resolvePaidCardMode("plus", status, "plus_monthly"), "interval-change");
});

test("premium user sees current exact offer, interval change, and downgrade", () => {
  const status = {
    effectivePlan: "premium",
    billingManaged: true,
    offerKey: "premium_monthly",
    pendingChangeState: "none",
  };
  assert.equal(resolvePaidCardMode("premium", status, "premium_monthly"), "current");
  assert.equal(resolvePaidCardMode("premium", status, "premium_annual"), "interval-change");
  assert.equal(resolvePaidCardMode("plus", status, "plus_monthly"), "downgrade");
});

test("scheduled interval target can cancel while other changes are blocked", () => {
  const status = {
    effectivePlan: "plus",
    billingManaged: true,
    offerKey: "plus_monthly",
    pendingChangeState: "scheduled",
    pendingPlan: "plus",
    pendingOfferKey: "plus_annual",
  };
  assert.equal(resolvePaidCardMode("plus", status, "plus_monthly"), "current");
  assert.equal(resolvePaidCardMode("plus", status, "plus_annual"), "pending-change");
  assert.equal(resolvePaidCardMode("premium", status, "premium_annual"), "pending-blocked");
});

test("scheduled downgrade target can cancel while another downgrade interval is blocked", () => {
  const status = {
    effectivePlan: "premium",
    billingManaged: true,
    offerKey: "premium_monthly",
    pendingChangeState: "scheduled",
    pendingPlan: "plus",
    pendingOfferKey: "plus_annual",
  };
  assert.equal(resolvePaidCardMode("plus", status, "plus_annual"), "pending-change");
  assert.equal(resolvePaidCardMode("plus", status, "plus_monthly"), "pending-blocked");
});

test("unmanaged basic-tier user with no billing relationship falls back to checkout, never portal", () => {
  const status = { effectivePlan: null, billingManaged: false, pendingChangeState: "none" };
  assert.equal(resolvePaidCardMode("plus", status, "plus_monthly"), "checkout");
});

test("unknown pending state blocks non-current changes", () => {
  const status = {
    effectivePlan: "plus",
    billingManaged: true,
    offerKey: "plus_monthly",
    pendingChangeState: "unknown",
  };
  assert.equal(resolvePaidCardMode("plus", status, "plus_monthly"), "current");
  assert.equal(resolvePaidCardMode("plus", status, "plus_annual"), "pending-unknown");
  assert.equal(resolvePaidCardMode("premium", status, "premium_monthly"), "pending-unknown");
});

test("legacy status without offerKey still preserves current-plan fallback", () => {
  const status = { effectivePlan: "premium", billingManaged: true, pendingChangeState: "unknown" };
  assert.equal(resolvePaidCardMode("premium", status, "premium_annual"), "current");
});

test("confirm result with paymentResult succeeded is treated as success", () => {
  assert.deepEqual(resolveConfirmOutcome({ action: "upgrade_now", paymentResult: "succeeded" }), {
    status: "success",
  });
});

test("confirm result with no paymentResult field is treated as success for scheduled changes", () => {
  assert.deepEqual(resolveConfirmOutcome({ action: "interval_change_at_period_end" }), { status: "success" });
  assert.deepEqual(resolveConfirmOutcome({ action: "downgrade_at_period_end" }), { status: "success" });
});

test("confirm result with paymentResult requires_action is NOT treated as success", () => {
  const outcome = resolveConfirmOutcome({ action: "upgrade_now", paymentResult: "requires_action" });
  assert.notEqual(outcome.status, "success");
  assert.deepEqual(outcome, { status: "requires_action" });
});

test("confirm result with paymentResult failed is NOT treated as success", () => {
  const outcome = resolveConfirmOutcome({ action: "upgrade_now", paymentResult: "failed" });
  assert.notEqual(outcome.status, "success");
  assert.deepEqual(outcome, { status: "failed" });
});
