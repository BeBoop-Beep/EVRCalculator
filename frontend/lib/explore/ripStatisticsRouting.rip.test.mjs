import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// ripStatisticsRouting.js imports through the "@/" alias, which bare node:test
// cannot resolve — inline its one dependency and evaluate the module, exactly
// as ripStatisticsRouting.test.mjs does.
const here = path.dirname(fileURLToPath(import.meta.url));
const read = (file) => fs.readFileSync(path.resolve(here, file), "utf8");
const slugifySource = read("../../utils/slugify.js")
  .split("export function")
  .join("function")
  .split("toSetSlug")
  .join("toCanonicalSetSlug");
const source = read("ripStatisticsRouting.js");
const moduleSource = source
  .split(/\r?\n/)
  .filter((line) => !line.startsWith("import "))
  .join("\n");
const { buildTcgSetHrefFromTarget, resolveSetDetailTab } = await import(
  `data:text/javascript;base64,${Buffer.from(`${slugifySource}\n${moduleSource}`, "utf8").toString("base64")}`
);

test("bare and invalid set tabs resolve to the overview-backed RIP destination", () => {
  assert.ok(source.includes('const SET_DETAIL_DEFAULT_TAB = "overview"'));
  assert.equal(resolveSetDetailTab(undefined), "overview");
  assert.equal(resolveSetDetailTab(""), "overview");
  assert.equal(resolveSetDetailTab("not-a-tab"), "overview");
  assert.equal(resolveSetDetailTab("rip"), "overview");
});

test("market is a canonical set-detail tab, not an overview alias", () => {
  assert.ok(source.includes('new Set(["overview", "market", "cards", "pull-rates", "insights"])'));
  assert.equal(resolveSetDetailTab("market"), "market");
  assert.equal(resolveSetDetailTab("MARKET"), "market");
  assert.ok(!source.includes('market: "overview"'), "market must never alias back to overview/RIP");
});

test("every canonical tab round-trips through the set href builder", () => {
  const target = { target_type: "set", target_id: "uuid-1", name: "Ascended Heroes" };
  for (const tab of ["overview", "market", "cards", "pull-rates", "insights"]) {
    assert.equal(
      buildTcgSetHrefFromTarget(target, { tab }),
      `/TCGs/Pokemon/Sets/ascended-heroes?tab=${tab}`,
      `${tab} survives href construction`
    );
    assert.equal(resolveSetDetailTab(tab), tab);
  }
});

test("legacy routes and user-facing aliases remain compatible", () => {
  assert.ok(source.includes('rip: "overview"'));
  assert.ok(source.includes('analysis: "insights"'));
  assert.ok(source.includes('analytics: "insights"'));
  assert.equal(resolveSetDetailTab("analysis"), "insights");
  assert.equal(resolveSetDetailTab("analytics"), "insights");
  // Existing indexed URLs must keep working untouched.
  assert.equal(resolveSetDetailTab("overview"), "overview");
  assert.equal(resolveSetDetailTab("insights"), "insights");
  assert.equal(resolveSetDetailTab("cards"), "cards");
  assert.equal(resolveSetDetailTab("pull-rates"), "pull-rates");
});

test("same-set tab links keep the canonical set route", () => {
  assert.ok(source.includes('params.set("tab", tab)'));
  assert.ok(source.includes('`${TCG_SETS_BASE_PATH}/${encodeURIComponent(slug)}`'));
});
