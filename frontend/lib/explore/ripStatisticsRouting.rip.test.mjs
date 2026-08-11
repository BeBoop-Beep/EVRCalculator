import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const source = fs.readFileSync(path.resolve(path.dirname(new URL(import.meta.url).pathname.slice(1)), "ripStatisticsRouting.js"), "utf8");

test("bare and invalid set tabs resolve to the overview-backed RIP destination", () => {
  assert.ok(source.includes('const SET_DETAIL_DEFAULT_TAB = "overview"'));
  assert.ok(source.includes('rip: "overview"'));
});

test("legacy routes and new user-facing aliases remain compatible", () => {
  assert.ok(source.includes('new Set(["overview", "cards", "pull-rates", "insights"])'));
  assert.ok(source.includes('analysis: "insights"'));
});

test("same-set tab links keep the canonical set route", () => {
  assert.ok(source.includes('params.set("tab", tab)'));
  assert.ok(source.includes('`${TCG_SETS_BASE_PATH}/${encodeURIComponent(slug)}`'));
});
