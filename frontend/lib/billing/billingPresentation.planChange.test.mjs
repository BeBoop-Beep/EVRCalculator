import assert from "node:assert/strict";
import { test } from "node:test";

import {
  downgradeConfirmationCopy,
  pendingChangeCopy,
  upgradeConfirmationCopy,
} from "./billingPresentation.mjs";

test("pendingChangeCopy returns null when nothing is scheduled", () => {
  assert.equal(pendingChangeCopy({ pendingChangeState: "none" }), null);
  assert.equal(pendingChangeCopy({ pendingChangeState: "unknown" }), null);
});

test("pendingChangeCopy describes a scheduled downgrade", () => {
  const copy = pendingChangeCopy({
    pendingChangeState: "scheduled",
    pendingPlan: "plus",
    pendingChangeEffectiveAt: Math.floor(new Date("2027-03-05T00:00:00Z").getTime() / 1000),
  });
  assert.match(copy, /Index Plus/);
  assert.match(copy, /2027/);
});

test("upgradeConfirmationCopy formats amount and renewal date", () => {
  const copy = upgradeConfirmationCopy({
    amountDueNow: 1500,
    currency: "usd",
    nextRenewalAt: Math.floor(new Date("2027-04-01T00:00:00Z").getTime() / 1000),
  });
  assert.match(copy.dueNowLabel, /\$15\.00/);
  assert.equal(copy.bodyLines.length, 2);
  assert.match(copy.bodyLines[1], /2027/);
});

test("downgradeConfirmationCopy describes retained access and no charge", () => {
  const copy = downgradeConfirmationCopy({
    currentPlanUntil: Math.floor(new Date("2027-03-05T00:00:00Z").getTime() / 1000),
  });
  assert.equal(copy.bodyLines.length, 3);
  assert.match(copy.bodyLines[0], /Index Premium until/);
  assert.match(copy.bodyLines[2], /No charge today/);
});
