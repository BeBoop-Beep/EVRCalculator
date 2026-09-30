import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const root = new URL("../../../../../", import.meta.url);
const read = (path) => readFileSync(new URL(path, root), "utf8");

test("all Activity POST proxies use the bounded shared no-reshape forwarder", () => {
  const routes = [
    "activity/route.js",
    "activity/capabilities/route.js",
    "activity/constituents/route.js",
    "activity/instrument/route.js",
  ];
  for (const route of routes) {
    const source = read(`app/api/market/explorer/${route}`);
    assert.match(source, /export async function POST/);
    assert.match(source, /proxyMarketActivity/);
  }
  const proxy = read("lib/explore/marketActivityProxy.js");
  for (const token of [
    "authorization",
    "cookie",
    'cache: "no-store"',
    '"Cache-Control": "private, no-store"',
    'Vary: "Cookie, Authorization"',
    "status: response.status",
    "MARKET_ACTIVITY_PROXY_UNAVAILABLE",
  ])
    assert.ok(proxy.includes(token), token);
  assert.doesNotMatch(
    proxy,
    /SERVICE_ROLE|SUPABASE_SERVICE|provider.*key|DATABASE_URL/i,
  );
});
