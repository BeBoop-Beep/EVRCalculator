import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (relative) => readFileSync(new URL(relative, import.meta.url), "utf8");
const helper = read("../../../lib/rankings/cardProxyResponse.js");
const routes = [
  read("./card-collector-appeal/route.js"),
  read("./card-ranking-facets/route.js"),
  read("./card-chase-efficiency/route.js"),
];

test("all Card proxies forward credentials and use the JSON failure boundary", () => {
  for (const source of routes) {
    assert.match(source, /headers\.Authorization = authorization/);
    assert.match(source, /headers\.Cookie = cookie/);
    assert.match(source, /cardProxyResponse\(\(\) => fetch/);
  }
});

test("Card proxy boundary is private JSON, preserves upstream status, and maps network failure to 503", () => {
  assert.match(helper, /NextResponse\.json\(payload, \{ status: response\.status/);
  assert.match(helper, /status: 503/);
  assert.match(helper, /"Cache-Control": "private, no-store"/);
  assert.match(helper, /Vary: "Cookie, Authorization"/);
  assert.match(helper, /Card Rankings backend returned an invalid response/);
});
