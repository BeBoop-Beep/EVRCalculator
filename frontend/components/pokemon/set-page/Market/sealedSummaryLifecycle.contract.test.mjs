import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relative) => fs.readFileSync(path.join(here, relative), "utf8");
const mobile = read("./SetMarketMobile.jsx");
const mobileValue = read("./SetMarketMobileSetValue.jsx");
const richMarket = read("../rich/RichMarketSetTab.jsx");
const richOverview = read("../rich/market/RichMarketOverviewSection.jsx");
const hook = read("../../../../hooks/pokemon/usePokemonSetSealedSummary.js");

test("mobile and desktop guarantee one identity-keyed summary load on mount", () => {
  assert.match(mobile, /enabled: Boolean\(setId\)/);
  assert.match(richMarket, /enabled: isDesktopHeroComposition/);
  assert.doesNotMatch(mobile, /settled\(setValue/);
  const summaryOwner = richMarket.slice(richMarket.indexOf("const desktopSealedSummaryState"), richMarket.indexOf("const desktopSealedSummaryState") + 900);
  assert.doesNotMatch(summaryOwner, /marketCriticalSettled/);
  assert.match(hook, /request\.setId !== resolvedSetId/);
  assert.match(hook, /state\.setId === resolvedSetId/);
});

test("idle loading and error remain selectable request states, distinct from unavailable", () => {
  for (const source of [mobileValue, richOverview]) {
    assert.match(source, /\["idle", "loading", "error"\]/);
    assert.match(source, /Loading Sealed market/);
  }
  assert.match(mobileValue, /sealedSummaryState\.status === "error"/);
  assert.match(hook, /isUnavailableSealedMarketError\(error\).*status: "unavailable"/s);
  assert.match(hook, /status: "error"/);
});

test("success uses prepared consumer history without set-specific exceptions", () => {
  for (const source of [mobileValue, richOverview]) {
    assert.match(source, /setPageConsumerMarket/);
    assert.match(source, /setMarket\.history/);
    for (const forbidden of ["Paldea Evolved", "White Flare", "Prismatic Evolutions", "Surging Sparks"]) {
      assert.equal(source.includes(forbidden), false);
    }
  }
});
