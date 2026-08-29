import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "../..");
const read = (relative) => fs.readFileSync(path.join(frontend, relative), "utf8").replace(/\r\n/g, "\n");

test("Rankings default route uses only lightweight publications", () => {
  const source = read("app/Explore/page.js");
  assert.ok(source.includes("RankingsLazyClient"));
  assert.ok(source.includes("getPokemonSetRouteDirectory"));
  assert.ok(!source.includes("getRipStatisticsTargets"), "Overall route must not build the canonical RIP cohort before a rankings lens needs it");
  assert.ok(!source.includes("getOverallProductRankings"), "Overall route must not fetch Product rankings before Product is selected");
  assert.ok(!source.includes("ProductFamilyRankingsClient"), "legacy all-lenses client must stay off the initial Rankings route");
});

test("Rankings analytical lenses are code-split and data-lazy", () => {
  const source = read("components/explore/RankingsLazyClient.jsx");
  for (const moduleName of [
    "OpeningEconomicsOverall",
    "OpeningEconomicsEras",
    "EraRankings",
    "SetPackMetrics",
    "ExploreTableClient",
    "CardChaseEfficiencyRankings",
    "RankingsProductLensClient",
  ]) {
    assert.ok(source.includes(`dynamic(() => import(\"./${moduleName}\")`), `${moduleName} must stay dynamically imported`);
  }
  assert.ok(source.includes('/api/explore/rankings/lens?lens=sets'));
  assert.ok(source.includes('/api/explore/rankings/lens?lens=eras'));
});

test("canonical Set rankings cohort is isolated behind the Sets lens endpoint", () => {
  const source = read("app/api/explore/rankings/lens/route.js");
  assert.ok(source.includes('if (lens === "sets")'));
  assert.ok(source.includes("projectRankingsTargets"));
  assert.ok(source.includes("isPublicAnalyticsEligiblePokemonSet"));
});

test("set canonical route uses the slim route directory on every tab", () => {
  const source = read("app/TCGs/Pokemon/Sets/[setSlug]/page.js");
  assert.ok(source.includes("getPokemonSetRouteDirectory({ limit: 150 })"));
  assert.ok(!source.includes("getRipStatisticsTargets"), "set URL resolution must never build the canonical rankings cohort");
  assert.ok(!source.includes("useSlimSetDirectory"), "tab-specific routing must not regress to heavyweight discovery");
});

test("set analytics runtime is split out of the initial route chunk", () => {
  const source = read("components/pokemon/set-page/PokemonSetPageClient.jsx");
  assert.ok(source.includes("dynamic("));
  assert.ok(source.includes('import("@/components/explore/RipStatisticsPageClient")'));
  assert.ok(source.includes("ssr: false"));
  assert.ok(!/^import RipStatisticsPageClient/m.test(source));
});

test("card and sealed-product server detail reads use bounded Next cache windows", () => {
  const card = read("lib/pokemon/pokemonCardDetailServer.js");
  const product = read("lib/pokemon/sealedProductDetailServer.js");
  for (const source of [card, product]) {
    assert.ok(source.includes("revalidate: DETAIL_REVALIDATE_SECONDS"));
    assert.ok(!source.includes('cache: "no-store"'));
  }
});
