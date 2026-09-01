import assert from "node:assert/strict";import fs from "node:fs";import test from "node:test";
const success=fs.readFileSync(new URL("../../components/billing/BillingSuccessClient.jsx",import.meta.url),"utf8");
const cancel=fs.readFileSync(new URL("./cancel/page.js",import.meta.url),"utf8");
test("success trusts billing status, not query strings, and refreshes canonical auth",()=>{assert.match(success,/pollBillingConfirmation/);assert.match(success,/refreshUser/);assert.doesNotMatch(success,/searchParams|plan=premium|index_plan/);assert.match(success,/still being confirmed/);});
test("cancel means abandoned checkout only",()=>{assert.match(cancel,/Checkout canceled/);assert.match(cancel,/No changes were made to your membership/);assert.doesNotMatch(cancel,/cancel.*subscription/i);});
