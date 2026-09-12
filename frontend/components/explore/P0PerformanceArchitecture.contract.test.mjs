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
    "SetRankingsHub",
    "CardChaseEfficiencyRankings",
    "RankingsProductLensClient",
  ]) {
    assert.ok(source.includes(`import(\"./${moduleName}\")`), `${moduleName} must stay dynamically imported`);
  }
  assert.ok(source.includes('/api/explore/rankings/lens?lens=sets'));
  assert.ok(source.includes('/api/explore/rankings/lens?lens=eras'));
  assert.ok(source.includes('const [lens, setActiveLens]'));
  assert.ok(!source.includes('setAnalysisLens'), "Set sub-navigation belongs to the lazy Set hub");
  const hub = read("components/explore/SetRankingsHub.jsx");
  for (const moduleName of ["SetRipScoreLeaderboard", "SetPackMetrics", "ExploreTableClient"]) assert.ok(hub.includes(`import("./${moduleName}")`));
  assert.ok(!hub.includes("fetch("), "Set tabs must reuse the cohort supplied by RankingsLazyClient");
});

test("canonical Set rankings cohort is isolated behind the Sets lens endpoint", () => {
  const source = read("app/api/explore/rankings/lens/route.js");
  const projection = read("lib/explore/setRankingsLensProjection.mjs");

  assert.ok(source.includes('if (lens === "sets")'));
  assert.ok(source.includes('preparedLensPayloadForRequest("sets", request)'));
  assert.ok(source.includes("projectSetRankingsLensTargets"));
  assert.ok(projection.includes("projectRankingsClientPublicSetLeaderboard"));
  assert.ok(source.includes("isPublicAnalyticsEligiblePokemonSet"));

  assert.ok(
    !source.includes("getRipStatisticsTargets"),
    "Sets lens must continue consuming the prepared backend lens rather than rebuilding the heavyweight cohort in Next"
  );
});

test("set canonical route uses the slim route directory on every tab", () => {
  const source = read("app/TCGs/Pokemon/Sets/[setSlug]/page.js");
  assert.ok(source.includes("getPokemonSetRouteDirectory({ limit: 200 })"));
  assert.ok(!source.includes("getRipStatisticsTargets"), "set URL resolution must never build the canonical rankings cohort");
  assert.ok(!source.includes("useSlimSetDirectory"), "tab-specific routing must not regress to heavyweight discovery");
});

test("set analytics runtime is split out of the initial route chunk", () => {
  const entrypoint = read("components/pokemon/set-page/PokemonSetPageClient.jsx");
  const runtime = read("components/pokemon/set-page/runtime/PokemonSetRuntimeShell.jsx");
  assert.ok(entrypoint.includes("dynamic("));
  assert.ok(entrypoint.includes('import("@/components/pokemon/set-page/PokemonSetRichPageClient")'));
  assert.ok(entrypoint.includes("ssr: false"));
  assert.ok(runtime.includes('dynamic(() => import("@/components/explore/RipStatisticsPageClient")'));
  assert.ok(runtime.includes("ssr: false"));
  assert.ok(!/^import RipStatisticsPageClient/m.test(entrypoint));
  assert.ok(!/^import RipStatisticsPageClient/m.test(runtime));
});

test("Recharts named imports stay optimized across analytical routes", () => {
  const source = read("next.config.mjs");
  assert.ok(source.includes('optimizePackageImports: ["recharts"]'));
});

test("card and sealed-product detail reads dedupe per render without sharing entitled payloads", () => {
  const card = read("lib/pokemon/pokemonCardDetailServer.js");
  const product = read("lib/pokemon/sealedProductDetailServer.js");
  for (const source of [card, product]) {
    assert.ok(source.includes("cache(async function"), "React cache must dedupe identical reads within one server render");
    assert.ok(source.includes('cache: "no-store"'), "identity-sensitive detail must not enter a shared Next cache");
    assert.ok(source.includes("getBackendRequestAuthHeaders"));
  }
  assert.ok(card.includes('url.searchParams.set("variant_id", variantId)'), "card request identity must include the selected variant");
  assert.ok(product.includes("encodeURIComponent(id)"), "product request identity must include the product id");
});
