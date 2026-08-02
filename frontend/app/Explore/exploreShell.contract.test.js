/**
 * Explore page shell contract (refinement Phase 2).
 *
 * Guards the composition decisions, not the styling: no outer page context
 * box, no visible page title, and the two first-row modules as siblings of one
 * grid fed by a single already-fetched target list.
 */

const fs = require("fs");
const path = require("path");
const test = require("node:test");
const assert = require("node:assert/strict");

const pagePath = path.resolve(__dirname, "page.js");

function readPage() {
  return fs.readFileSync(pagePath, "utf8");
}

// --- A. Page shell -------------------------------------------------------

test("the visible Explore page heading is gone but a semantic h1 remains", () => {
  const source = readPage();
  assert.ok(
    source.includes('<h1 className="sr-only">Explore</h1>'),
    "an h1 must remain for document structure, visually hidden via the screen-reader utility"
  );
  assert.ok(
    !/<h1(?![^>]*sr-only)/.test(source),
    "no visible h1 may be rendered on the Explore page"
  );
  assert.ok(
    !source.includes('text-2xl font-semibold text-[var(--text-primary)]">Explore<'),
    "the old visible page title must not come back"
  );
});

test("the obsolete outer page context wrapper is gone", () => {
  const source = readPage();
  assert.ok(!source.includes("dashboard-container"), "the outer context box must not wrap the Explore page");
  assert.ok(!source.includes("!border-0"), "the wrapper's override hacks must be gone with it");
});

test("a sensible max content width and horizontal gutters are preserved", () => {
  const source = readPage();
  assert.ok(source.includes("max-w-7xl"), "content must stay bounded on very large screens");
  assert.ok(/px-4[^"]*sm:px-6[^"]*lg:px-8/.test(source), "page gutters must be preserved");
});

test("document metadata and route semantics are preserved", () => {
  const source = readPage();
  assert.ok(source.includes("export const metadata"), "the route must still describe itself for document metadata");
  assert.ok(source.includes("export default async function ExplorePage({ searchParams })"), "route signature unchanged");
});

// --- B. Layout -----------------------------------------------------------

test("Explore modules use the required accessible DOM order", () => {
  const source = readPage();
  const movers = source.indexOf("<ExploreMarketMovers");
  const rankings = source.indexOf("<ExploreTopRankings");
  const bestSets = source.indexOf("<ExploreTableClient");
  assert.ok(movers > 0 && movers < rankings && rankings < bestSets);
});

test("Top Rankings is full-width rather than a secondary desktop sidebar", () => {
  const source = readPage();
  assert.ok(source.includes('className="space-y-5"'));
  assert.ok(!source.includes("xl:grid-cols-[minmax(0,2fr)_minmax(19rem,1fr)]"));
});

test("movers and rankings load independently with one global movers request", () => {
  const source = readPage();
  assert.ok(source.includes("Promise.allSettled"));
  assert.ok(source.includes("getExploreMarketMovers()"));
});

test("either module can render when the other has no data", () => {
  const source = readPage();
  // Both modules receive the SAME already-resolved list and the same error
  // flag, and each owns its own empty/error branch — neither can throw the
  // other out of the tree.
  assert.ok(source.includes("<ExploreTableClient targets={leaderboardTargets} loadError={rankingsLoadError} />"));
  assert.ok(source.includes("<ExploreTopRankings targets={leaderboardTargets} loadError={rankingsLoadError} />"));
});

// --- D. No regression ----------------------------------------------------

test("the redesign introduces exactly one request per prepared snapshot family", () => {
  const source = readPage();
  const fetches = source.match(/getRipStatisticsTargets\(/g) || [];
  assert.equal(fetches.length, 1, "Explore must still make exactly one targets request");
  assert.equal((source.match(/getExploreMarketMovers\(\)/g) || []).length, 1);
});

test("public-analytics eligibility filtering is unchanged", () => {
  const source = readPage();
  assert.ok(
    source.includes("targets.filter(isPublicAnalyticsEligiblePokemonSet)"),
    "the eligibility filter must still gate every consumer on the page"
  );
});
