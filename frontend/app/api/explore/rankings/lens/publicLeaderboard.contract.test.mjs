import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const route = fs.readFileSync(new URL("./route.js", import.meta.url), "utf8");
const lazy = fs.readFileSync(new URL("../../../../../components/explore/RankingsLazyClient.jsx", import.meta.url), "utf8");

test("Set lens always applies the narrow public leaderboard projection", () => {
  const sets = route.slice(route.indexOf('if (lens === "sets")'), route.indexOf('if (lens === "eras")'));
  assert.match(sets, /projectRankingsClientPublicSetLeaderboard\(rankTargets\(eligible\)\)/);
  assert.doesNotMatch(sets, /canViewRankingsIntelligence:/);
});

test("Era lens returns the prepared public contract without an entitlement lock", () => {
  const eras = route.slice(route.indexOf('if (lens === "eras")'), route.indexOf('if (lens === "products")'));
  assert.match(eras, /status: "available"/);
  assert.match(eras, /eraSetStrength/);
  assert.doesNotMatch(eras, /status: "locked"|rankingsIntelligence !== true/);

  const loader = lazy.slice(lazy.indexOf("const loadEra"), lazy.indexOf("const loadSets"));
  assert.doesNotMatch(loader, /canViewRankingsIntelligence|authStatus !== "resolved"/);
});

test("Product and Card entitlement branches remain present", () => {
  assert.match(route, /if \(lens === "products"\)/);
  assert.match(lazy, /if \(!canViewCardChaseEfficiency\) return Promise\.resolve\(null\)/);
});
