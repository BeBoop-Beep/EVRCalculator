import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const here = path.dirname(fileURLToPath(import.meta.url));
const statisticsSource = fs.readFileSync(path.join(here, "../explore/ripStatisticsServer.js"), "utf8");
const landingSource = fs.readFileSync(path.join(here, "landingHeroServer.js"), "utf8");
const apiSource = fs.readFileSync(path.join(here, "../../../backend/api/main.py"), "utf8");

test("homepage uses the dedicated public summary and never the entitlement-sensitive cohort", () => {
  assert.match(landingSource, /getHomepageRankingsSummary\(\)/);
  assert.doesNotMatch(landingSource, /getRipStatisticsTargets\(/);
});

test("homepage summary sends fixed public headers and no ambient request state", () => {
  const start = statisticsSource.indexOf("async function fetchHomepageRankingsSummaryUncached");
  const end = statisticsSource.indexOf("export async function getHomepageRankingsSummary", start);
  const reader = statisticsSource.slice(start, end);
  assert.match(reader, /fetchHomepageRankingsSummaryUncached\(\)/);
  assert.match(reader, /getPublicBackendRequestHeaders\(\)/);
  assert.doesNotMatch(reader, /getBackendRequestAuthHeaders\(|headers:\s*await\s+getBackend/);
});

test("homepage endpoint has no auth, cookie, or plan parameter", () => {
  const start = apiSource.indexOf('@app.get("/explore/rankings/homepage-summary")');
  const end = apiSource.indexOf("\n@app.", start + 1);
  const route = apiSource.slice(start, end < 0 ? undefined : end);
  assert.match(route, /get_pokemon_homepage_benchmark_summary_payload/);
  assert.match(route, /def get_explore_rankings_homepage_summary\(limit: Optional\[str\] = Query\(default=None\)\):/);
  assert.doesNotMatch(route, /resolve_plan_context\(|authorization:\s*|cookie:\s*/i);
});

test("completed homepage reads are not warm-cached across Benchmark publication flips", () => {
  assert.match(statisticsSource, /let homepageSummaryInFlight = null/);
  assert.doesNotMatch(statisticsSource, /homepageSummaryCache|HOMEPAGE_SUMMARY_TTL/);
});
