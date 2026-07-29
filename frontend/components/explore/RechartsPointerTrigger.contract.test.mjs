import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (relativePath) =>
  fs.readFileSync(path.resolve(here, relativePath), "utf8").replace(/\r\n/g, "\n");

const client = read("RipStatisticsPageClient.jsx");
const packValue = read("PackValueHistoryChart.jsx");

const setValueChart = client.slice(
  client.indexOf("function SetValueLineChart("),
  client.indexOf("function SetValueTrendCard(")
);

test("Set Value Trend switches trigger by pointer mode", () => {
  assert.ok(
    setValueChart.includes('trigger={isCoarsePointer ? "click" : "hover"}'),
    "the tooltip trigger follows the active pointer"
  );
  assert.ok(setValueChart.includes("const isCoarsePointer = usePointerMode() === POINTER_MODE_COARSE;"));
  // Everything else about the tooltip is unchanged.
  assert.ok(setValueChart.includes("content={<SetValueTooltip />}"));
  assert.ok(setValueChart.includes('cursor={{ stroke: "rgba(255,255,255,0.16)", strokeWidth: 1 }}'));
});

test("Opening Profit vs Cost switches trigger by pointer mode", () => {
  assert.ok(packValue.includes('trigger={isCoarsePointer ? "click" : "hover"}'));
  assert.ok(packValue.includes('import usePointerMode, { POINTER_MODE_COARSE } from "@/hooks/usePointerMode";'));
  assert.ok(packValue.includes("content={<TrendTooltip packCost={packCost} variant={variant} />}"));
});

test("neither chart simulates hover or disables it globally", () => {
  for (const [name, source] of [["set value", setValueChart], ["opening profit vs cost", packValue]]) {
    assert.ok(!source.includes("new MouseEvent"), `${name} must not synthesise mouse events`);
    assert.ok(!source.includes('trigger="click"'), `${name} must not hardcode click and strip desktop hover`);
    assert.ok(!source.includes('trigger="hover"'), `${name} must not hardcode hover and strip touch`);
  }
});

test("both charts keep exactly one ResponsiveContainer", () => {
  assert.equal((setValueChart.match(/<ResponsiveContainer/g) || []).length, 1);
  assert.equal((packValue.match(/<ResponsiveContainer/g) || []).length, 1);
});

test("the pointer mode is seeded from capability, not from the first tap", () => {
  // Correction 4: if the mode were only learned from the first pointerdown, the
  // first deliberate touch would be spent switching modes and the user would
  // have to tap twice.
  const hook = read("../../hooks/usePointerMode.js");
  assert.ok(
    hook.includes('window.matchMedia("(hover: hover) and (pointer: fine)")'),
    "the mode is seeded from device capability on mount"
  );
  assert.ok(
    hook.includes('window.addEventListener("pointerdown", handlePointerDown, { capture: true, passive: true })'),
    "the listener runs in the capture phase so the same gesture already sees the new mode"
  );
  assert.ok(hook.includes("POINTER_MODE_FINE)"), "SSR and first paint default to fine so desktop hover never flashes off");
});
