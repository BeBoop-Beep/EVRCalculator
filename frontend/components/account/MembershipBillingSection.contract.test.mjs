import assert from "node:assert/strict";import fs from "node:fs";import test from "node:test";
const source=fs.readFileSync(new URL("./MembershipBillingSection.jsx",import.meta.url),"utf8");
test("billing UI is extracted, accessible, and configuration driven",()=>{assert.match(source,/id="billing"/);assert.match(source,/aria-labelledby/);assert.match(source,/purchasableOfferKeys|selectableOffers/);assert.match(source,/Pricing pending/);assert.doesNotMatch(source,/\$\d/);assert.doesNotMatch(source,/localStorage/);});
test("pricing pending reflects missing catalog pricing, not managed-subscriber checkout availability",()=>{assert.match(source,/!summary\.monthly && !summary\.annual/);assert.doesNotMatch(source,/offers\.every\(key => offerPlan\(key\) !== plan\)/);});
test("portal and checkout happen only on explicit button actions",()=>{assert.match(source,/type="button" onClick=\{portal\}/);assert.match(source,/createCheckoutSession\(offerKey\)/);assert.match(source,/createCustomerPortalSession\(\)/);assert.match(source,/if\(action\) return/);});
test("server auth refresh updates global feature-facing user state",()=>{assert.match(source,/await refreshUser\(\)/);});
