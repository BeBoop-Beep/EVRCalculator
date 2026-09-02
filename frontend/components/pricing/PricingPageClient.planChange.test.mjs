import assert from "node:assert/strict";
import { test } from "node:test";

// Imported from the pure, dependency-free module (re-exported by
// PricingPageClient.jsx) rather than the .jsx file directly: this repo's
// tsx/esbuild test runner cannot parse the JSX in AuthContext.js when it is
// pulled in transitively via a .jsx component import (a pre-existing gap —
// every other component test in the repo works around it with
// fs.readFileSync source-string assertions instead of a real import). See
// task-10-report.md for details.
import { resolvePaidCardMode } from "./resolvePaidCardMode.mjs";
import { resolveConfirmOutcome } from "./resolveConfirmOutcome.mjs";

test("basic user sees checkout for both plus and premium", () => {
  const status = { effectivePlan: null, billingManaged: false, pendingChangeState: "none" };
  assert.equal(resolvePaidCardMode("plus", status), "checkout");
  assert.equal(resolvePaidCardMode("premium", status), "checkout");
});

test("plus user sees current-plan on plus card and upgrade on premium card", () => {
  const status = { effectivePlan: "plus", billingManaged: true, pendingChangeState: "none" };
  assert.equal(resolvePaidCardMode("plus", status), "current");
  assert.equal(resolvePaidCardMode("premium", status), "upgrade");
});

test("premium user sees current-plan on premium card and downgrade on plus card", () => {
  const status = { effectivePlan: "premium", billingManaged: true, pendingChangeState: "none" };
  assert.equal(resolvePaidCardMode("premium", status), "current");
  assert.equal(resolvePaidCardMode("plus", status), "downgrade");
});

test("premium user with scheduled downgrade sees pending mode on plus card", () => {
  const status = { effectivePlan: "premium", billingManaged: true, pendingChangeState: "scheduled", pendingPlan: "plus" };
  assert.equal(resolvePaidCardMode("plus", status), "pending-downgrade");
});

test("unmanaged basic-tier user with no billing relationship falls back to checkout, never portal", () => {
  const status = { effectivePlan: null, billingManaged: false, pendingChangeState: "none" };
  assert.equal(resolvePaidCardMode("plus", status), "checkout");
});

test("plus user with unknown pending state sees pending-unknown on premium card, not upgrade", () => {
  const status = { effectivePlan: "plus", billingManaged: true, pendingChangeState: "unknown" };
  assert.equal(resolvePaidCardMode("premium", status), "pending-unknown");
});

test("premium user with unknown pending state sees pending-unknown on plus card, not downgrade or pending-downgrade", () => {
  const status = { effectivePlan: "premium", billingManaged: true, pendingChangeState: "unknown" };
  assert.equal(resolvePaidCardMode("plus", status), "pending-unknown");
});

test("unknown pending state never demotes the current-plan card", () => {
  const status = { effectivePlan: "premium", billingManaged: true, pendingChangeState: "unknown" };
  assert.equal(resolvePaidCardMode("premium", status), "current");
});

test("confirm result with paymentResult succeeded is treated as success", () => {
  assert.deepEqual(resolveConfirmOutcome({ action: "upgrade_now", paymentResult: "succeeded" }), {
    status: "success",
  });
});

test("confirm result with no paymentResult field (downgrade) is treated as success", () => {
  assert.deepEqual(resolveConfirmOutcome({ action: "schedule_downgrade" }), { status: "success" });
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
