import assert from "node:assert/strict";
import test from "node:test";
import { createCardsPageState, mergeCardsPage } from "./setCardsControllerState.mjs";

test("Cards page one replaces a previous request scope", () => {
  const previous = { ...createCardsPageState("set-a"), scopeKey: "old", cards: [{ id: "old" }] };
  const next = mergeCardsPage(previous, { cards: [{ id: "new" }], pagination: { page: 1 } }, {
    setId: "set-a", scopeKey: "new-scope", requestedPage: 1,
  });
  assert.deepEqual(next.cards.map((card) => card.id), ["new"]);
  assert.equal(next.scopeKey, "new-scope");
});

test("Cards later pages append in server order and deduplicate stable card identities", () => {
  const previous = { ...createCardsPageState("set-a"), scopeKey: "scope", page: 1, cards: [{ id: "one" }, { id: "two" }] };
  const next = mergeCardsPage(previous, {
    cards: [{ id: "two" }, { id: "three" }], pagination: { page: 2, hasNextPage: false },
  }, { setId: "set-a", scopeKey: "scope", requestedPage: 2 });
  assert.deepEqual(next.cards.map((card) => card.id), ["one", "two", "three"]);
  assert.equal(next.page, 2);
});

test("Cards never append a page from a changed set or request scope", () => {
  const previous = { ...createCardsPageState("set-a"), scopeKey: "scope-a", cards: [{ id: "old" }] };
  for (const identity of [
    { setId: "set-b", scopeKey: "scope-a" },
    { setId: "set-a", scopeKey: "scope-b" },
  ]) {
    const next = mergeCardsPage(previous, { cards: [{ id: "fresh" }] }, { ...identity, requestedPage: 2 });
    assert.deepEqual(next.cards.map((card) => card.id), ["fresh"]);
  }
});
