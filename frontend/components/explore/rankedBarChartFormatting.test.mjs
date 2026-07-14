import assert from "node:assert/strict";
import test from "node:test";

import {
  COMPACT_BAR_CHART_PADDING,
  COMPACT_BAR_ROW_HEIGHT,
  NICE_SHARE_DOMAIN_CEILINGS,
  formatAbbreviatedCount,
  formatAbbreviatedCurrency,
  getCompactChartHeight,
  getNiceShareDomainMaximum,
  sortRowsByValueDescending,
  truncateChartLabel,
} from "./rankedBarChartFormatting.mjs";

test("getNiceShareDomainMaximum picks the first readable ceiling >= the actual maximum", () => {
  assert.equal(getNiceShareDomainMaximum(29.2), 30);
  assert.equal(getNiceShareDomainMaximum(46.0), 50);
  assert.equal(getNiceShareDomainMaximum(71.6), 75);
  assert.equal(getNiceShareDomainMaximum(0.4), 1);
  assert.equal(getNiceShareDomainMaximum(100), 100);
  assert.equal(getNiceShareDomainMaximum(30), 30);
  // A 100%+ or unusable maximum still yields a sane full-scale/floor domain.
  assert.equal(getNiceShareDomainMaximum(140), 100);
  assert.equal(getNiceShareDomainMaximum(0), NICE_SHARE_DOMAIN_CEILINGS[0]);
  assert.equal(getNiceShareDomainMaximum(null), NICE_SHARE_DOMAIN_CEILINGS[0]);
  assert.equal(getNiceShareDomainMaximum("nope"), NICE_SHARE_DOMAIN_CEILINGS[0]);
});

test("sortRowsByValueDescending ranks without mutating and keeps every source row object", () => {
  const rows = [
    { label: "Illustration Rare", value: 900_000 },
    { label: "Special Illustration Rare", value: 6_255_870.74 },
    { label: "Double Rare", value: 120_000 },
    { label: "Regular Reverse", value: 1_100_000 },
  ];
  const inputSnapshot = rows.map((row) => row.label);

  const sorted = sortRowsByValueDescending(rows, "value");

  assert.deepEqual(
    sorted.map((row) => row.label),
    ["Special Illustration Rare", "Regular Reverse", "Illustration Rare", "Double Rare"]
  );
  // All source rows remain included, as the same untouched objects (exact
  // tooltip data unchanged), and the input array order is not mutated.
  assert.equal(sorted.length, rows.length);
  sorted.forEach((row) => assert.ok(rows.includes(row), "sorted output must reuse the source row objects"));
  assert.deepEqual(rows.map((row) => row.label), inputSnapshot);
});

test("sortRowsByValueDescending tolerates missing/invalid values and non-array input", () => {
  const sorted = sortRowsByValueDescending([{ value: null }, { value: 5 }, {}], "value");
  assert.equal(sorted.length, 3);
  assert.equal(sorted[0].value, 5);
  assert.deepEqual(sortRowsByValueDescending(null), []);
});

test("getCompactChartHeight keeps many-row charts compact", () => {
  assert.equal(getCompactChartHeight(10), 10 * COMPACT_BAR_ROW_HEIGHT + COMPACT_BAR_CHART_PADDING); // ~246px
  assert.equal(getCompactChartHeight(17), 17 * COMPACT_BAR_ROW_HEIGHT + COMPACT_BAR_CHART_PADDING); // ~407px
  assert.equal(getCompactChartHeight(0), COMPACT_BAR_ROW_HEIGHT + COMPACT_BAR_CHART_PADDING);
  // 17 states must never balloon back into a 600-800px list.
  assert.ok(getCompactChartHeight(17) < 450);
});

test("truncateChartLabel truncates with ellipsis and preserves its input", () => {
  const long = "Special Illustration Rare Golden Variant";
  const truncated = truncateChartLabel(long, 26);
  assert.ok(truncated.endsWith("…"));
  assert.ok(truncated.length <= 26);
  assert.equal(long, "Special Illustration Rare Golden Variant", "input string must be preserved");
  assert.equal(truncateChartLabel("Baseline", 26), "Baseline");
  assert.equal(truncateChartLabel(null, 26), "");
});

test("formatAbbreviatedCount keeps counts exact below a million and abbreviates above", () => {
  assert.equal(formatAbbreviatedCount(463196), "463,196");
  assert.equal(formatAbbreviatedCount(1200), "1,200");
  assert.equal(formatAbbreviatedCount(1_000_000), "1.0M");
  assert.equal(formatAbbreviatedCount(2_450_000), "2.5M");
  assert.equal(formatAbbreviatedCount(1_200_000_000), "1.2B");
  assert.equal(formatAbbreviatedCount(0), "0");
  assert.equal(formatAbbreviatedCount(null), "—");
});

test("formatAbbreviatedCurrency abbreviates to the chart's compact right-column style", () => {
  assert.equal(formatAbbreviatedCurrency(6255870.74), "$6.26M");
  assert.equal(formatAbbreviatedCurrency(8742029.87), "$8.74M");
  assert.equal(formatAbbreviatedCurrency(1200), "$1.2K");
  assert.equal(formatAbbreviatedCurrency(845.2), "$845");
  assert.equal(formatAbbreviatedCurrency(1_250_000_000), "$1.25B");
  assert.equal(formatAbbreviatedCurrency(-4500), "-$4.5K");
  assert.equal(formatAbbreviatedCurrency(null), "—");
});
