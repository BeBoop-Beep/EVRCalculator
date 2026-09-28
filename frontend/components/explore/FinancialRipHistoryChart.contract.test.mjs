import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./FinancialRipHistoryChart.jsx", import.meta.url), "utf8");
const model = readFileSync(new URL("./financialRipHistoryModel.mjs", import.meta.url), "utf8");

test("uses the Financial RIP history reader and no legacy benchmark reader", () => {
  assert.ok(source.includes("readFinancialRipHistory"));
  assert.ok(!source.includes("readBenchmarkHistory"));
  assert.ok(source.indexOf("shouldFetchFinancialRipHistory") < source.indexOf("readFinancialRipHistory(selected"));
});

test("locked access is a synthetic frosted preview with no chart data dependency", () => {
  assert.ok(source.includes("data-financial-rip-history-locked"));
  assert.ok(source.includes("backdrop-blur-md"));
  assert.ok(source.includes("INDEX_PLAN_PLUS"));
  assert.ok(source.includes("<LockedPreview />"));
});

test("controls, gap behavior, moving reference, and responsive frame are explicit", () => {
  for (const label of ["Sets", "Eras", "Overall Financial RIP"]) assert.ok(source.includes(label));
  for (const window of ["30D", "3M", "6M", "1Y", "ALL"]) assert.ok(model.includes(`key: "${window}"`));
  assert.equal((source.match(/connectNulls=\{false\}/g) || []).length, 2);
  assert.ok(source.includes("<ChartFrame"));
  assert.ok(source.includes("h-[20rem] sm:h-[24rem] desk:h-[28rem]"));
  assert.ok(source.includes("MAX_FINANCIAL_RIP_SET_SELECTION"));
});
test("refresh and failure preserve the last successful certified chart", () => {
  assert.ok(source.includes('setRequest((current) => ({ ...current, status: "loading"'));
  assert.ok(source.includes("const display = request.view"));
  assert.ok(source.includes("The latest refresh failed, so the last successful history remains visible."));
  assert.ok(source.includes("Updating history…"));
});

test("chart copy is valid UTF-8 and uses the canonical Rankings upgrade source", () => {
  assert.ok(source.includes("Pokémon-wide Overall Financial RIP reference"));
  assert.ok(source.includes('source="rankings"'));
  assert.doesNotMatch(source, /PokÃ|â€¦|Â·/);
});

