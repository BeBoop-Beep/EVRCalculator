import assert from "node:assert/strict";
import { test } from "node:test";

import {
  BillingClientError,
  cancelScheduledPlanChange,
  confirmPlanChange,
  previewPlanChange,
} from "./billingClient.mjs";

function stubFetch(responseBody, { ok = true, status = 200 } = {}) {
  const calls = [];
  global.fetch = async (url, init) => {
    calls.push({ url, init });
    return {
      ok,
      status,
      json: async () => responseBody,
      text: async () => JSON.stringify(responseBody),
    };
  };
  return calls;
}

test("previewPlanChange posts offerKey to the preview proxy route", async () => {
  const calls = stubFetch({ action: "upgrade_now", amountDueNow: 1500 });
  const result = await previewPlanChange("premium_monthly");
  assert.equal(calls[0].url, "/api/billing/change-plan/preview");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), { offerKey: "premium_monthly" });
  assert.equal(result.amountDueNow, 1500);
});

test("confirmPlanChange posts offerKey and previewToken", async () => {
  const calls = stubFetch({ action: "upgrade_now", paymentResult: "succeeded" });
  const result = await confirmPlanChange("premium_monthly", "tok-abc");
  assert.equal(calls[0].url, "/api/billing/change-plan/confirm");
  assert.deepEqual(JSON.parse(calls[0].init.body), { offerKey: "premium_monthly", previewToken: "tok-abc" });
  assert.equal(result.paymentResult, "succeeded");
});

test("cancelScheduledPlanChange posts with no body", async () => {
  const calls = stubFetch({ cancelled: true });
  const result = await cancelScheduledPlanChange();
  assert.equal(calls[0].url, "/api/billing/change-plan/cancel-scheduled");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(result.cancelled, true);
});

test("previewPlanChange throws BillingClientError on failure response", async () => {
  stubFetch({ detail: { code: "PLAN_CHANGE_NOT_ALLOWED" } }, { ok: false, status: 409 });
  await assert.rejects(() => previewPlanChange("plus_annual"), BillingClientError);
});
