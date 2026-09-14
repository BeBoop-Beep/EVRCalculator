import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8").replace(/\r\n/g, "\n");
const browse = read("./MarketExplorerBrowse.jsx");
const screens = read("./MarketExplorerScreens.jsx");
const preparedProxy = read("../../app/api/market/explorer/prepared/route.js");
const queryProxy = read("../../app/api/market/explorer/query/route.js");
const preflightProxy = read("../../app/api/market/explorer/query/preflight/route.js");

test("directory unavailable, canonical empty, and search no-match have distinct UI copy", () => {
  assert.match(browse, /Market directory is temporarily unavailable\./);
  assert.match(browse, /No canonical \$\{categoryLabel\} are currently published\./);
  assert.match(browse, /No matching \$\{categoryLabel\}\./);
  assert.match(browse, /location\?\.reload\(\)/);
});

test("directory interaction remains local, bounded, and keyboard accessible", () => {
  assert.doesNotMatch(browse, /fetch\s*\(/);
  assert.match(browse, /max-h-\[min\(25rem,55vh\)\]/);
  assert.match(browse, /overflow-y-auto/);
  assert.match(browse, /event\.key === "ArrowDown"/);
  assert.match(browse, /event\.key === "ArrowUp"/);
  assert.match(browse, /event\.key === "Enter"/);
  assert.match(browse, /event\.key === "Escape"/);
  assert.match(browse, /close\(true\)/);
  assert.match(browse, /aria-pressed=\{active\}/);
});

test("prepared Screen and query proxies preserve safe structured transport codes", () => {
  assert.match(preparedProxy, /PREPARED_PROXY_UNAVAILABLE/);
  assert.match(queryProxy, /MARKET_EXPLORER_QUERY_PROXY_UNAVAILABLE/);
  assert.match(preflightProxy, /QUERY_PREFLIGHT_PROXY_UNAVAILABLE/);
  assert.match(screens, /httpStatus: response\.status/);
  assert.match(screens, /errorCode:/);
});
