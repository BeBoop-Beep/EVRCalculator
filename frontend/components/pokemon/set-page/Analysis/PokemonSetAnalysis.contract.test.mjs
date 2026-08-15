import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const root = process.cwd();
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

test("analysis is a child route with accessible internal navigation and return path", () => {
  const page = read("app/TCGs/Pokemon/Sets/[setSlug]/analysis/page.js");
  const client = read("components/pokemon/set-page/Analysis/PokemonSetAnalysisClient.jsx");
  assert.match(page, /PokemonSetAnalysisClient/);
  assert.match(client, /aria-label="Analysis sections"/);
  assert.match(client, /aria-current=/);
  assert.match(client, /Back to Set/);
  assert.match(client, /section=\$\{activeSection\}/);
});

test("analysis reads canonical contracts and reuses production deep dives", () => {
  const client = read("components/pokemon/set-page/Analysis/PokemonSetAnalysisClient.jsx");
  assert.match(client, /resolveCanonicalRipV7\(critical\)/);
  assert.match(client, /<FinancialRipV3Breakdown canonical=\{canonical\}/);
  assert.match(client, /<CollectorAppealBreakdown canonical=\{canonical\}/);
  assert.match(client, /<RipDistributionChart/);
  assert.doesNotMatch(client, /Ascended Heroes|Journey Together|Surging Sparks/);
});

test("disabled Analysis is hidden from RIP and direct URLs redirect to the same set", () => {
  const flags = read("config/featureFlags.js");
  const page = read("app/TCGs/Pokemon/Sets/[setSlug]/analysis/page.js");
  const rip = read("components/explore/RipDecisionPage.jsx");
  const shell = read("components/explore/RipStatisticsPageClient.jsx");
  assert.match(flags, /POKEMON_SET_ANALYSIS_ENABLED = false/);
  assert.match(rip, /View full Financial RIP breakdown/);
  assert.match(rip, /View full Collector Appeal breakdown/);
  assert.doesNotMatch(rip, /<FinancialRipV3Breakdown/);
  assert.match(shell, /financialAnalysisHref=\{POKEMON_SET_ANALYSIS_ENABLED \?/);
  assert.match(shell, /collectorAnalysisHref=\{POKEMON_SET_ANALYSIS_ENABLED \?/);
  assert.match(shell, /: null\}/);
  assert.match(page, /if \(!POKEMON_SET_ANALYSIS_ENABLED\)/);
  assert.match(page, /redirect\(buildTcgSetHrefFromSlug\(setSlug\)\)/);
});
