import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

// This component imports "@/..." aliases that only resolve under Next's own
// bundler, not the plain tsx test runner -- so it is verified as source text
// here (the same pattern this repo already uses for other "@/"-importing
// components) rather than actually rendered.
const source = readFileSync(
  path.join(path.dirname(fileURLToPath(import.meta.url)), "SetMarketSignals.jsx"),
  "utf8"
);

// Regression coverage for the invisible donut: a conic-gradient() background
// with ANY unresolved var() reference is invalid CSS in its ENTIRETY, so the
// whole ring silently renders with no fill at all rather than just that one
// stop. --positive, --negative and --surface-card are not defined anywhere in
// globals.css, so referencing them here made the donut disappear while the
// plain-text percentages next to it (unaffected by the bad var) rendered fine.
test("the breadth donut never references the undefined --positive/--negative/--surface-card custom properties", () => {
  assert.ok(!source.includes("var(--positive)"), "must not reference the undefined --positive custom property");
  assert.ok(!source.includes("var(--negative)"), "must not reference the undefined --negative custom property");
  assert.ok(!source.includes("var(--surface-card)"), "must not reference the undefined --surface-card custom property");
});

test("the breadth donut's conic-gradient is built from the canonical market color constants", () => {
  assert.ok(
    source.includes('import { NEGATIVE_VALUE_COLOR, POSITIVE_VALUE_COLOR } from "@/lib/explore/interpretationTone";'),
    "must import the same canonical positive/negative colors every other delta surface uses"
  );
  assert.match(
    source,
    /conic-gradient\(\$\{POSITIVE_VALUE_COLOR\}[^`]*\$\{NEGATIVE_VALUE_COLOR\}/,
    "the arc order (advancing, then declining, then unchanged) must use the resolved color constants"
  );
  // The center disc must use a real defined surface token.
  assert.ok(source.includes('backgroundColor: "var(--surface-panel)"'), "the center disc must use the real --surface-panel token");
});

test("the donut and left-aligned legend form one centered bounded visual group", () => {
  assert.match(source, /mx-auto mt-3 grid w-fit/);
  assert.ok(source.includes("grid-cols-[96px_auto]"));
  assert.ok(source.includes('className="flex w-24 justify-center max-[430px]:mx-auto" data-market-breadth-donut-column'));
  assert.ok(source.includes('text-left max-[430px]:w-full max-[430px]:grid-cols-3" data-market-breadth-legend'));
  assert.ok(source.includes("max-[430px]:grid-cols-1"), "430px and below may stack without overflow");
});

test("excluded tracked cards are disclosed separately and never become a fourth donut slice", () => {
  assert.match(source, /data-breadth-excluded/);
  assert.match(source, /excludedCount\.toLocaleString\("en-US"\).*N\/A · insufficient comparable pricing/s);
  assert.match(source, /totalTrackedCount\.toLocaleString\("en-US"\).*tracked cards total/s);
  assert.equal((source.match(/const legend = \[/g) || []).length, 1);
  assert.doesNotMatch(source.slice(source.indexOf("const legend = ["), source.indexOf("];", source.indexOf("const legend = ["))), /N\/A|Excluded/);
});
