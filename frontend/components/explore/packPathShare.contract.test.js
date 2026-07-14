const path = require("path");
const { pathToFileURL } = require("url");
const test = require("node:test");
const assert = require("node:assert/strict");

const packPathSharePath = path.resolve(__dirname, "packPathShare.mjs");

async function loadModule() {
  return import(pathToFileURL(packPathSharePath).href);
}

const ONE_MILLION = 1_000_000;

test("formatPackPathShare returns 0.0% for exactly zero and 100.0% for exactly one", async () => {
  const { formatPackPathShare } = await loadModule();
  assert.equal(formatPackPathShare(0), "0.0%");
  assert.equal(formatPackPathShare(1), "100.0%");
});

test("formatPackPathShare never collapses a nonzero rare God Pack share to 0.0%", async () => {
  const { formatPackPathShare } = await loadModule();
  const godShare = formatPackPathShare(464 / ONE_MILLION);
  assert.notEqual(godShare, "0.0%");
  // 0.0464% -> 3 decimals -> "0.046%" (acceptable band is ~0.046% or 0.05%).
  assert.equal(godShare, "0.046%");
});

test("formatPackPathShare never rounds a below-100% Normal share up to 100.0%", async () => {
  const { formatPackPathShare } = await loadModule();
  const normalShare = formatPackPathShare(999_536 / ONE_MILLION);
  assert.notEqual(normalShare, "100.0%");
  // 99.9536% -> keeps the remainder visible -> "99.954%" (~99.95%).
  assert.ok(normalShare.startsWith("99.95"), `expected ~99.95%, got ${normalShare}`);
});

test("formatPackPathShare uses adaptive decimal precision across bands", async () => {
  const { formatPackPathShare } = await loadModule();
  assert.equal(formatPackPathShare(0.5), "50.0%"); // 1 decimal where sufficient
  assert.equal(formatPackPathShare(0.05), "5.0%");
  assert.equal(formatPackPathShare(0.005), "0.50%"); // 0.5% -> 2 decimals
  assert.equal(formatPackPathShare(0.0005), "0.050%"); // 0.05% -> 3 decimals
  assert.equal(formatPackPathShare(0.00005), "<0.01%"); // below display precision
  assert.equal(formatPackPathShare(0.9999999), ">99.99%"); // mirror near the top edge
});

test("formatPackPathShare guards non-finite and negative input", async () => {
  const { formatPackPathShare } = await loadModule();
  assert.equal(formatPackPathShare(null), "0.0%");
  assert.equal(formatPackPathShare(undefined), "0.0%");
  assert.equal(formatPackPathShare(Number.NaN), "0.0%");
  assert.equal(formatPackPathShare(-0.1), "0.0%");
});

test("formatShareFromCounts divides counts and guards a zero/absent total", async () => {
  const { formatShareFromCounts } = await loadModule();
  assert.equal(formatShareFromCounts(0, ONE_MILLION), "0.0%");
  assert.notEqual(formatShareFromCounts(464, ONE_MILLION), "0.0%");
  assert.equal(formatShareFromCounts(464, ONE_MILLION), "0.046%");
  assert.notEqual(formatShareFromCounts(999_536, ONE_MILLION), "100.0%");
  assert.equal(formatShareFromCounts(ONE_MILLION, ONE_MILLION), "100.0%");
  assert.equal(formatShareFromCounts(5, 0), "0.0%");
  assert.equal(formatShareFromCounts(5, null), "0.0%");
});

test("formatImpliedOdds reports 1-in-N only for positive, meaningfully-rare counts", async () => {
  const { formatImpliedOdds } = await loadModule();
  assert.equal(formatImpliedOdds(464, ONE_MILLION), "About 1 in 2,155 packs");
  // Zero-count paths never show implied odds.
  assert.equal(formatImpliedOdds(0, ONE_MILLION), null);
  // A dominant path that rounds to "1 in 1" is suppressed as noise.
  assert.equal(formatImpliedOdds(999_536, ONE_MILLION), null);
  assert.equal(formatImpliedOdds(5, 0), null);
});

test("isRarePathShare flags nonzero sub-threshold shares only", async () => {
  const { isRarePathShare, RARE_PATH_VISIBILITY_RATIO } = await loadModule();
  assert.equal(RARE_PATH_VISIBILITY_RATIO, 0.005);
  assert.equal(isRarePathShare(464 / ONE_MILLION), true);
  assert.equal(isRarePathShare(0), false);
  assert.equal(isRarePathShare(0.5), false);
  assert.equal(isRarePathShare(0.005), false); // exactly at the threshold is not "below"
});

test("buildPackPathDisplayRows boosts a rare special path to a recognizable ~7% while keeping real counts", async () => {
  const { buildPackPathDisplayRows, SPECIAL_PATH_MIN_DISPLAY_SHARE } = await loadModule();
  const input = [
    { key: "normal", name: "Normal", count: 999_536, fill: "teal", isSpecial: false },
    { key: "god_pack", name: "God Pack", count: 464, fill: "amber", isSpecial: true },
  ];
  const rows = buildPackPathDisplayRows(input);

  const god = rows.find((r) => r.key === "god_pack");
  const normal = rows.find((r) => r.key === "normal");

  // The God Pack's true share is 0.0464% but its DISPLAY weight is ~7% (in band).
  assert.equal(SPECIAL_PATH_MIN_DISPLAY_SHARE, 0.07);
  assert.ok(god.displayWeight >= 0.05 && god.displayWeight <= 0.1, `god displayWeight ${god.displayWeight} not in 5-10% band`);
  assert.ok(normal.displayWeight >= 0.9 && normal.displayWeight <= 0.95, `normal displayWeight ${normal.displayWeight}`);
  // Display weights fill the ring.
  assert.ok(Math.abs(god.displayWeight + normal.displayWeight - 1) < 1e-9);

  // Real counts and passthrough fields are untouched (labels stay truthful).
  assert.equal(god.count, 464);
  assert.equal(normal.count, 999_536);
  assert.equal(god.fill, "amber");
  assert.equal(god.name, "God Pack");
  // Pure: does not mutate the input rows.
  assert.equal(input[1].count, 464);
  assert.ok(!("displayWeight" in input[1]));
});

test("buildPackPathDisplayRows leaves an already-large special path roughly proportional", async () => {
  const { buildPackPathDisplayRows } = await loadModule();
  const rows = buildPackPathDisplayRows([
    { key: "normal", count: 800_000, isSpecial: false },
    { key: "god_pack", count: 200_000, isSpecial: true }, // 20% real, already >7%
  ]);
  const god = rows.find((r) => r.key === "god_pack");
  const normal = rows.find((r) => r.key === "normal");
  // Above the boost floor, the display weight tracks the true share (~20%/80%).
  assert.ok(Math.abs(god.displayWeight - 0.2) < 1e-9, `god displayWeight ${god.displayWeight}`);
  assert.ok(Math.abs(normal.displayWeight - 0.8) < 1e-9, `normal displayWeight ${normal.displayWeight}`);
});

test("buildPackPathDisplayRows gives zero-count paths zero weight (no visible sector)", async () => {
  const { buildPackPathDisplayRows } = await loadModule();
  const rows = buildPackPathDisplayRows([
    { key: "normal", count: 1_000_000, isSpecial: false },
    { key: "demi_god_pack", count: 0, isSpecial: true },
    { key: "god_pack", count: 0, isSpecial: true },
  ]);
  assert.equal(rows.find((r) => r.key === "demi_god_pack").displayWeight, 0);
  assert.equal(rows.find((r) => r.key === "god_pack").displayWeight, 0);
  assert.equal(rows.find((r) => r.key === "normal").displayWeight, 1);
});

test("buildPackPathDisplayRows tolerates empty/zero-total input", async () => {
  const { buildPackPathDisplayRows } = await loadModule();
  assert.deepEqual(buildPackPathDisplayRows([]), []);
  const allZero = buildPackPathDisplayRows([{ key: "normal", count: 0, isSpecial: false }]);
  assert.equal(allZero[0].displayWeight, 0);
});
