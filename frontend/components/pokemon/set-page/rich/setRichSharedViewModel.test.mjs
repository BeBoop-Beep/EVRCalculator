import assert from "node:assert/strict";
import test from "node:test";
import { selectSetRichSharedViewModel } from "./setRichSharedViewModel.mjs";

test("identity and canonical target card count are authoritative", () => {
  const model = selectSetRichSharedViewModel({ setId: "set-1", shell: { set: { id: "set-1", cardCount: 181 } }, target: { id: "set-1", card_count: 180 } });
  assert.deepEqual(model.identity, { setId: "set-1", valid: true });
  assert.equal(model.cardCount, 180);
});
test("summary fallback wins over a differently-defined shell identity count", () => {
  const model = selectSetRichSharedViewModel({
    setId: "set-1",
    shell: { set: { id: "set-1", cardCount: 305 }, summary: { simulated_set_value_card_count: 295 } },
  });
  assert.equal(model.cardCount, 295);
});
test("target and RIP bootstrap provide narrow fallback without card rows", () => {
  assert.equal(selectSetRichSharedViewModel({ setId: "set-1", target: { id: "set-1", card_count: 99 } }).cardCount, 99);
  assert.equal(selectSetRichSharedViewModel({ setId: "set-1", ripBootstrap: { summary: { simulated_set_value_card_count: 88 } } }).cardCount, 88);
});
test("wrong-set shell is rejected", () => assert.equal(selectSetRichSharedViewModel({ setId: "set-1", shell: { set: { id: "set-2", cardCount: 100 } } }).identity.valid, false));
test("missing and zero values stay unavailable", () => {
  assert.equal(selectSetRichSharedViewModel({ setId: "set-1" }).cardCount, null);
  assert.equal(selectSetRichSharedViewModel({ setId: "set-1", target: { card_count: 0 } }).cardCount, null);
});
test("publication identity remains narrow", () => assert.deepEqual(selectSetRichSharedViewModel({ setId: "set-1", shell: { meta: { marketAsOfDate: "2026-08-31" } }, ripBootstrap: { calculationRunId: "run-1" } }).publication, { calculationRunId: "run-1", marketAsOfDate: "2026-08-31" }));
