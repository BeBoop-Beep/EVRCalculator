import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// Regression coverage for the "logout mid-session" path: a user who is
// entitled (Index+/Premium) when RankingsLazyClient mounts must see paid
// values disappear and locks appear on the very next render after their
// auth/entitlement state flips to anonymous -- without requiring a full
// window.location.reload(). See task-5-brief.md for the scenario.
//
// This repo has no jest/@testing-library/react and RankingsLazyClient's
// entitlement hook (useRankingsAccess -> useAuth -> next/navigation's
// usePathname/useRouter) cannot be mounted with react-test-renderer without
// a full Next.js router shim (the same constraint task-1-report.md hit).
// So, consistent with the other *.contract.test.mjs files beside this one
// (RankingsLazyClient.state.contract.test.mjs), this test proves the
// refetch/identity wiring by source inspection of the exact mechanism the
// component relies on at runtime.

const here = path.dirname(fileURLToPath(import.meta.url));
const lazySource = fs.readFileSync(path.join(here, "RankingsLazyClient.jsx"), "utf8").replace(/\r\n/g, "\n");
const accessSource = fs
  .readFileSync(path.join(here, "..", "..", "lib", "rankings", "useRankingsAccess.js"), "utf8")
  .replace(/\r\n/g, "\n");

test("requestKey is derived fresh from the live auth identity and access mode every call", () => {
  // No memoization/caching of identity inside the hook itself -- every call
  // to useRankingsAccess() (i.e. every render) recomputes requestKey from
  // the current auth context, so a logout produces a new requestKey on the
  // very next render.
  assert.match(accessSource, /const identity = String\(auth\?\.user\?\.id \|\| auth\?\.user\?\.user_id \|\| auth\?\.user\?\.email \|\| "anonymous"\)/);
  assert.match(accessSource, /requestKey: `\$\{identity\}:\$\{access\.accessMode\}`/);
});

test("the session cache identity is keyed on requestKey, so a downgrade invalidates the previous entitled cache", () => {
  assert.match(lazySource, /createRankingsSessionCache\(`\$\{requestKey\}:\$\{publicationIdentity\}`\)/);
  // useMemo must depend on requestKey, not just publicationIdentity, or a
  // logout would keep serving the entitled-session cache instance.
  const memoCall = lazySource.slice(
    lazySource.indexOf("createRankingsSessionCache(`${requestKey}:${publicationIdentity}`)"),
    lazySource.indexOf("createRankingsSessionCache(`${requestKey}:${publicationIdentity}`)") + 200,
  );
  assert.match(memoCall, /\[requestKey, publicationIdentity\]/);
});

test("data-fetch callbacks depend on the identity-scoped sessionCache, so a downgrade forces a real refetch", () => {
  const loadEraBlock = lazySource.slice(lazySource.indexOf("const loadEra"), lazySource.indexOf("const loadSets"));
  const loadSetsBlock = lazySource.slice(lazySource.indexOf("const loadSets"), lazySource.indexOf("const warmProducts"));
  assert.match(loadEraBlock, /\}, \[rankingsMarketDate, sessionCache\]\);/);
  assert.match(loadSetsBlock, /\}, \[rankingsMarketDate, sessionCache\]\);/);

  // The mount/lens-change effects that invoke loadEra/loadSets must list the
  // callback itself as a dependency -- since the callback's identity changes
  // whenever sessionCache changes, this is what makes an auth downgrade
  // trigger a fresh fetch rather than replaying stale entitled data.
  assert.match(lazySource, /if \(lens === "eras" && eraLens === "rankings"\) loadEra\(\{ foreground: true \}\);\n {2}\}, \[lens, eraLens, loadEra\]\);/);
  assert.match(lazySource, /if \(lens === "sets"\) loadSets\(\{ foreground: true \}\);\n {2}\}, \[lens, loadSets\]\);/);
});

test("stale entitled results are hidden synchronously on the render after a downgrade, before any refetch resolves", () => {
  // visibleEraState/visibleSetsState fall back to an idle/empty shape the
  // instant setsState/eraState.cacheIdentity no longer matches the *current*
  // sessionCache.identity. Since sessionCache.identity flips synchronously
  // with requestKey on re-render, this guarantees the previously-visible
  // paid values (and the era/set data behind them) cannot leak into the
  // anonymous render even for one frame while the network refetch is
  // in flight.
  assert.match(
    lazySource,
    /const visibleEraState = eraState\.cacheIdentity === sessionCache\.identity \? eraState : \{ status: "idle", contract: null, marketDate: rankingsMarketDate \};/,
  );
  assert.match(
    lazySource,
    /const visibleSetsState = setsState\.cacheIdentity === sessionCache\.identity \? setsState : \{ status: "idle", targets: \[\], marketDate: rankingsMarketDate \};/,
  );
});

test("the paid entitlement prop passed to ExploreTableClient is the live value, not a cached/hardcoded one", () => {
  // Companion regression to Task 1: even if the fetch-driven set targets were
  // (incorrectly) to persist across a downgrade, the lock-vs-value decision
  // in ExploreTableClient must still be driven by the current render's
  // canViewRankingsIntelligence, not a value captured at mount.
  assert.match(lazySource, /canViewProductRipIntelligence=\{canViewRankingsIntelligence\}/);
});

test("no full-page reload is used to force the downgrade to take effect", () => {
  assert.doesNotMatch(lazySource, /window\.location\.reload/);
  assert.doesNotMatch(lazySource, /location\.reload\(\)/);
});
