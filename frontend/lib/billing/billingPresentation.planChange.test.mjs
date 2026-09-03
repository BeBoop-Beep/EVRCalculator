import assert from "node:assert/strict";
import { test } from "node:test";

import {
  downgradeConfirmationCopy,
  pendingChangeCopy,
  scheduledChangeConfirmationCopy,
  upgradeConfirmationCopy,
} from "./billingPresentation.mjs";

test("pendingChangeCopy returns null when nothing is scheduled", () => {
  assert.equal(pendingChangeCopy({ pendingChangeState: "none" }), null);
  assert.equal(pendingChangeCopy({ pendingChangeState: "unknown" }), null);
});

test("pendingChangeCopy describes a scheduled downgrade", () => {
  const copy = pendingChangeCopy({
    pendingChangeState: "scheduled",
    effectivePlan: "premium",
    pendingPlan: "plus",
    pendingOfferKey: "plus_annual",
    pendingChangeEffectiveAt: Math.floor(new Date("2027-03-05T00:00:00Z").getTime() / 1000),
  });
  assert.match(copy, /Index Plus/);
  assert.match(copy, /2027/);
});

test("pendingChangeCopy names same-tier billing interval changes", () => {
  const copy = pendingChangeCopy({
    pendingChangeState: "scheduled",
    effectivePlan: "plus",
    pendingPlan: "plus",
    pendingOfferKey: "plus_annual",
    pendingChangeEffectiveAt: Math.floor(new Date("2027-03-05T00:00:00Z").getTime() / 1000),
  });
  assert.match(copy, /annual billing/i);
  assert.match(copy, /2027/);
});

test("upgradeConfirmationCopy formats amount, renewal date, and recurring terms", () => {
  const copy = upgradeConfirmationCopy({
    amountDueNow: 1500,
    currency: "usd",
    nextRenewalAt: Math.floor(new Date("2027-04-01T00:00:00Z").getTime() / 1000),
  });
  assert.match(copy.dueNowLabel, /\$15\.00/);
  assert.equal(copy.bodyLines.length, 4);
  assert.match(copy.bodyLines[1], /2027/);
  assert.match(copy.bodyLines[2], /renew automatically/i);
  assert.match(copy.bodyLines[3], /cancel before a renewal/i);
  assert.match(copy.bodyLines[3], /prorated refund/i);
});

test("downgradeConfirmationCopy describes retained access, no charge, and recurring terms", () => {
  const copy = downgradeConfirmationCopy({
    currentPlanUntil: Math.floor(new Date("2027-03-05T00:00:00Z").getTime() / 1000),
  });
  assert.equal(copy.bodyLines.length, 5);
  assert.match(copy.bodyLines[0], /Index Premium until/);
  assert.match(copy.bodyLines[2], /No charge today/);
  assert.match(copy.bodyLines[3], /renew automatically/i);
  assert.match(copy.bodyLines[4], /cancel before a renewal/i);
  assert.match(copy.bodyLines[4], /prorated refund/i);
});

test("scheduledChangeConfirmationCopy describes monthly to annual without changing access", () => {
  const copy = scheduledChangeConfirmationCopy({
    currentPlanUntil: Math.floor(new Date("2027-03-05T00:00:00Z").getTime() / 1000),
    fromPlan: "plus",
    toPlan: "plus",
    fromOfferKey: "plus_monthly",
    toOfferKey: "plus_annual",
  });
  assert.match(copy.heading, /Index Plus billing/);
  assert.match(copy.bodyLines[0], /monthly billing until/i);
  assert.match(copy.bodyLines[1], /Annual billing begins/i);
  assert.match(copy.bodyLines[2], /No charge today/);
  assert.match(copy.bodyLines[3], /access do not change/i);
  assert.match(copy.bodyLines[4], /renew automatically yearly/i);
});

test("scheduledChangeConfirmationCopy preserves downgrade copy for cross-tier changes", () => {
  const copy = scheduledChangeConfirmationCopy({
    currentPlanUntil: Math.floor(new Date("2027-03-05T00:00:00Z").getTime() / 1000),
    fromPlan: "premium",
    toPlan: "plus",
    fromOfferKey: "premium_monthly",
    toOfferKey: "plus_annual",
  });
  assert.equal(copy.heading, "Change to Index Plus");
  assert.match(copy.bodyLines[0], /Index Premium until/);
});
