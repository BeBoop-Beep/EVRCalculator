import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  buildRipDecisionModel,
  isSameChaseCard,
  selectMarketChaseCards,
} from "./ripDecisionModel.mjs";

test("opening economics map only authoritative summary fields", () => {
  const model = buildRipDecisionModel({
    summary: {
      pack_cost: 5.49,
      mean_value: 3.12,
      median_value: 1.08,
      prob_profit: 0.187,
      expected_loss_per_pack: 3.41,
    },
  });
  assert.equal(model.packCost, 5.49);
  assert.equal(model.expectedValue, 3.12);
  assert.equal(model.typicalOpening, 1.08);
  assert.equal(model.recoverCostProbability, 0.187);
  assert.equal(model.expectedLoss, 3.41);
});

test("market chase cards are capped for a compact responsive section", () => {
  const chaseCards = Array.from({ length: 7 }, (_, index) => ({ id: index, name: `Card ${index}` }));
  assert.equal(selectMarketChaseCards(chaseCards).length, 4);
});

test("the canonical Top Chase is removed from the secondary market chases", () => {
  const topChase = { cardVariantId: "variant-mega-gengar-a", name: "Mega Gengar" };
  const cards = selectMarketChaseCards(
    [
      { cardVariantId: "variant-mega-gengar-a", name: "Mega Gengar" },
      { cardVariantId: "variant-pikachu", name: "Pikachu" },
      { cardVariantId: "variant-dragonite", name: "Dragonite" },
      { cardVariantId: "variant-charizard", name: "Charizard" },
    ],
    { excludeCard: topChase }
  );

  assert.deepEqual(
    cards.map((card) => card.name),
    ["Pikachu", "Dragonite", "Charizard"],
    "the section must begin with Pikachu, not repeat the Top Chase"
  );
});

// --- the variant -> card -> name fallback ladder ---------------------------

test("A: a market row with no variant id still matches on the shared card id", () => {
  const topChase = { cardVariantId: "variant-a", cardId: "card-x", name: "Mega Gengar ex" };
  const cards = selectMarketChaseCards(
    [
      { cardVariantId: null, cardId: "card-x", name: "Mega Gengar ex" },
      { cardVariantId: "variant-p", cardId: "card-p", name: "Pikachu" },
    ],
    { excludeCard: topChase }
  );

  assert.deepEqual(
    cards.map((card) => card.name),
    ["Pikachu"],
    "one side lacking variant identity must fall back to the card id both carry"
  );
  assert.equal(isSameChaseCard({ cardId: "card-x" }, topChase), true);
});

test("B: two known-different variants of one card never collapse", () => {
  const topChase = { cardVariantId: "variant-a", cardId: "card-x", name: "Mega Gengar ex" };
  const cards = selectMarketChaseCards(
    [{ cardVariantId: "variant-b", cardId: "card-x", name: "Mega Gengar ex" }],
    { excludeCard: topChase }
  );

  assert.equal(cards.length, 1, "differing variant ids are final; no fallback to card id or name");
  assert.equal(
    isSameChaseCard({ cardVariantId: "variant-b", cardId: "card-x" }, topChase),
    false
  );
});

test("C: with no usable ids on either side, normalized names decide", () => {
  assert.equal(isSameChaseCard({ name: "Mega Gengar ex" }, { name: "mega  gengar EX" }), true);
  assert.equal(isSameChaseCard({ name: "Pikachu" }, { name: "Dragonite" }), false);
});

test("D: same name but different known variants stays distinct", () => {
  assert.equal(
    isSameChaseCard(
      { cardVariantId: "variant-a", name: "Mega Gengar ex" },
      { cardVariantId: "variant-b", name: "Mega Gengar ex" }
    ),
    false,
    "a coincidental name match must not override differing variant identity"
  );
});

test("differing card ids are final and never fall through to names", () => {
  assert.equal(
    isSameChaseCard({ cardId: "card-x", name: "Pikachu" }, { cardId: "card-y", name: "Pikachu" }),
    false
  );
});

test("a nameless card cannot match another nameless card by default", () => {
  assert.equal(isSameChaseCard({}, {}), false, "absent identity is not a match");
  assert.equal(isSameChaseCard(null, { name: "Pikachu" }), false);
});

test("a different variant of the same Pokemon survives the Top Chase filter", () => {
  const cards = selectMarketChaseCards(
    [
      { cardVariantId: "variant-mega-gengar-a", cardId: "card-mega-gengar", name: "Mega Gengar" },
      { cardVariantId: "variant-mega-gengar-b", cardId: "card-mega-gengar", name: "Mega Gengar" },
    ],
    { excludeCard: { cardVariantId: "variant-mega-gengar-a", cardId: "card-mega-gengar", name: "Mega Gengar" } }
  );

  assert.deepEqual(
    cards.map((card) => card.cardVariantId),
    ["variant-mega-gengar-b"],
    "variant identity must not collapse two genuinely different chases"
  );
});

test("name matching is the last rung, used when ids cannot be compared on both sides", () => {
  // Both sides id-less: names are all there is, so the duplicate is removed.
  const byName = selectMarketChaseCards([{ name: "Mega Gengar" }, { name: "Pikachu" }], {
    excludeCard: { name: "mega  gengar" },
  });
  assert.deepEqual(byName.map((card) => card.name), ["Pikachu"]);

  // One side has a variant id and the other has none, so no id pair can be
  // compared and the ladder falls through to the name — which matches.
  const oneSidedId = selectMarketChaseCards([{ cardVariantId: "variant-a", name: "Mega Gengar" }], {
    excludeCard: { name: "Mega Gengar" },
  });
  assert.equal(oneSidedId.length, 0, "an uncomparable id pair falls back rather than giving up");
});

test("the obsolete invented decision-contract reader is gone", () => {
  const source = fs.readFileSync(
    path.resolve(path.dirname(new URL(import.meta.url).pathname.slice(1)), "ripDecisionModel.mjs"),
    "utf8"
  );
  assert.ok(!source.includes("selectRipDecisionFields"), "the broken reader must not return");
  // The invented shapes that made the previous pass silently render nulls.
  for (const invented of [
    "decisionMetrics",
    "decision_metrics",
    "openings_for_50_percent",
    "break_even_value",
    "odds_denominator",
    "spend_for_50_percent",
    "probability_per_opening",
  ]) {
    assert.ok(!source.includes(invented), `${invented} was never published by the backend`);
  }
  // This module must not parse the real contract either — that is one file's
  // job. Naming the boundary module in a comment is fine; reaching into the
  // contract's fields is not.
  assert.doesNotMatch(
    source,
    /ripDecision\??\.(topChase|sealedProducts|currentRunAvailable|products)/,
    "the decision contract must be parsed only in ripDecisionContract.mjs"
  );
  assert.ok(!source.includes("topChase"), "the canonical chase must not be reconstructed here");
});
