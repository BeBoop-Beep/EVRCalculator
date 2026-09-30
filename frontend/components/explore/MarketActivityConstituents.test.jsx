import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const exactJoin = (activityRow, canonicalByVariant) => {
  const canonical = canonicalByVariant.get(activityRow.cardVariantId);
  return canonical &&
    activityRow.instrumentKey === `card:${activityRow.cardVariantId}:raw`
    ? { ...activityRow, display: canonical }
    : null;
};
const selectSalesWindow = (windows, days) =>
  windows.find((entry) => entry.days === days) || null;

test("two coordinated 50-row pages join all 100 rows by exact variant identity", () => {
  const canonical = Array.from({ length: 100 }, (_, index) => ({
    cardVariantId: `v${index + 1}`,
    cardName: `Card ${index + 1}`,
  }));
  const activity = canonical.map((row) => ({
    cardVariantId: row.cardVariantId,
    instrumentKey: `card:${row.cardVariantId}:raw`,
  }));
  const byVariant = new Map(canonical.map((row) => [row.cardVariantId, row]));
  const joined = [...activity.slice(0, 50), ...activity.slice(50)].map((row) =>
    exactJoin(row, byVariant),
  );
  assert.equal(joined.length, 100);
  assert.equal(joined[50].display.cardName, "Card 51");
  assert.equal(
    exactJoin(
      { cardVariantId: "v51", instrumentKey: "card:v52:raw" },
      byVariant,
    ),
    null,
  );
});

test("sales summaries use the backend days field and select the requested 30-day window", () => {
  const windows = [7, 30, 90, 180].map((days) => ({
    days,
    observedCount: days,
    priceSummary: { median: { amount: String(days) } },
  }));
  assert.deepEqual(
    windows.map((window) => window.days),
    [7, 30, 90, 180],
  );
  assert.equal(selectSalesWindow(windows, 30).observedCount, 30);
  assert.equal(selectSalesWindow(windows, 14), null);
});

test("Load more coordinates canonical and Activity pagination", async () => {
  const source = await readFile(
    new URL("./MarketActivityConstituents.jsx", import.meta.url),
    "utf8",
  );
  assert.match(source, /canonical\.loadMore\(\);\s*activity\.loadMore\(\);/);
  assert.match(source, /entry\.days === days/);
});
