import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const root = join(process.cwd(), ".perf-audit", "fixtures", "set-rich-v1");
const manifest = JSON.parse(readFileSync(join(root, "manifest.json"), "utf8"));
const setIds = ["7a3dd188-4375-41af-94de-c5247fe0b1a6", "75cd439d-aaa2-41cb-86f3-2fefa5b26e29"];
const load = (pattern) => {
  const match = Object.entries(manifest.routes).find(([route]) => pattern.test(route));
  assert.ok(match, `missing fixture route ${pattern}`);
  return JSON.parse(readFileSync(join(root, match[1].file), "utf8"));
};

test("fixture manifest contains only public GET Pokemon contracts", () => {
  assert.equal(Object.keys(manifest.routes).length, 20);
  for (const [route, entry] of Object.entries(manifest.routes)) {
    assert.match(route, /^\/tcgs\/pokemon\//);
    assert.equal(entry.status, 200);
    assert.match(entry.file, /^[a-f0-9]{16}\.json$/);
  }
});

for (const id of setIds) {
  test(`${id} freezes complete Top Chase and both Market lenses`, () => {
    const chase = load(new RegExp(`${id}/market/top-chase\\?`));
    const cards = chase.topChaseCards || [];
    const histories = chase.topChaseCardHistories || {};
    assert.equal(cards.length, 10);
    assert.ok(cards.every((card) => Number(card.marketPrice) > 0));
    assert.ok(cards.every((card) => (histories[card.cardVariantId] || []).length >= 2));
    assert.equal(chase.meta?.topChaseCompleteness?.status, "complete");

    const market = load(new RegExp(`${id}/market/bootstrap\\?`));
    assert.ok((market.setValueHistoriesByScope?.standard || []).length >= 2);
    assert.equal(market.cardsMarket?.available, true);
    const sealed = load(new RegExp(`${id}/market/sealed-consumer$`));
    assert.ok(sealed && Object.keys(sealed).length > 0);
  });
}
