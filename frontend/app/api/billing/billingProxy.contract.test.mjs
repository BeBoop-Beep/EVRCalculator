import assert from "node:assert/strict";import fs from "node:fs";import test from "node:test";
const proxy=fs.readFileSync(new URL("../../../lib/billing/billingProxy.js",import.meta.url),"utf8");
const checkout=fs.readFileSync(new URL("./checkout-session/route.js",import.meta.url),"utf8");
const portal=fs.readFileSync(new URL("./customer-portal/route.js",import.meta.url),"utf8");
test("billing proxies forward auth privately and are never shared-cacheable",()=>{assert.match(proxy,/request\.headers\.get\("cookie"\)/);assert.match(proxy,/authorization/);assert.match(proxy,/cache: "no-store"/);assert.match(proxy,/"Cache-Control": "no-store"/);assert.match(proxy,/"Vary": "Cookie, Authorization"/);});
test("portal accepts no browser authority body and checkout forwards backend validation",()=>{assert.doesNotMatch(portal,/request\.json|customerId|returnUrl/);assert.match(checkout,/request\.json/);assert.match(checkout,/\/billing\/checkout-session/);});
