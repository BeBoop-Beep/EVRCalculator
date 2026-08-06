import test from "node:test";
import assert from "node:assert/strict";

import { selectMobileHeroModel } from "./mobileHeroModel.mjs";

const base = {
  setName: "Perfect Order",
  era: "Mega Evolution",
  logoUrl: "https://images.example/logo.png",
  setValue: { current: 663.14, deltaAmount: -115.78, deltaPercent: -14.9, windowLabel: "30D" },
  // `verdict` is deliberately still supplied by this fixture: it must be
  // IGNORED, not merely absent. It carried the retired interpretation engine's
  // label, which describes neither Financial RIP V3 nor Collector Appeal V3.
  rip: { label: "RIP Score", score: 100, tier: "S", rank: 1, cohortSize: 212, verdict: "Elite, some path risk" },
};

test("a complete set produces the brief's hero composition", () => {
  const model = selectMobileHeroModel(base);

  assert.equal(model.identity.name, "Perfect Order");
  assert.equal(model.identity.era, "Mega Evolution");
  assert.equal(model.identity.hasLogo, true);

  assert.equal(model.value.hasValue, true);
  assert.equal(model.value.amountText, "$663.14");
  assert.equal(model.value.direction, "negative");
  assert.equal(model.value.deltaText, "$115.78 · 14.9% · 30D");

  assert.equal(model.rip.hasRip, true);
  assert.equal(model.rip.scoreText, "100");
  assert.equal(model.rip.tierText, "S Tier");
  assert.equal(model.rip.rankText, "Rank #1");
  assert.equal("verdict" in model.rip, false, "the interpretation verdict is not part of the model");
  assert.equal(JSON.stringify(model).includes("Elite, some path risk"), false);
  assert.equal(model.rip.isActionable, true);
});

test("positive movement is signed the other way and never colour-only", () => {
  const model = selectMobileHeroModel({
    ...base,
    setValue: { current: 100, deltaAmount: 8.5, deltaPercent: 9.25, windowLabel: "7D" },
  });
  assert.equal(model.value.direction, "positive");
  // The magnitude is unsigned here; the caller renders a triangle glyph plus an
  // accessible label, so direction is never carried by colour alone.
  assert.equal(model.value.deltaText, "$8.50 · 9.3% · 7D");
});

test("zero movement reads as flat, not as a fake gain", () => {
  const model = selectMobileHeroModel({
    ...base,
    setValue: { current: 100, deltaAmount: 0, deltaPercent: 0, windowLabel: "30D" },
  });
  assert.equal(model.value.direction, "neutral");
  assert.equal(model.value.deltaText, "$0.00 · 0.0% · 30D");
});

test("a missing set value does not blank the hero", () => {
  const model = selectMobileHeroModel({ ...base, setValue: { current: null, deltaAmount: null, deltaPercent: null, windowLabel: "30D" } });
  assert.equal(model.value.hasValue, false);
  assert.equal(model.value.amountText, "—");
  assert.equal(model.value.deltaText, null);
  assert.equal(model.rip.hasRip, true, "RIP survives a missing set value");
});

test("missing RIP does not blank the hero", () => {
  const model = selectMobileHeroModel({ ...base, rip: { label: "RIP Score", score: null, tier: null, rank: null, cohortSize: null, verdict: null } });
  assert.equal(model.rip.hasRip, false);
  assert.equal(model.rip.isActionable, false, "an empty RIP row must not advertise a tap target");
  assert.equal(model.value.hasValue, true, "Set Value survives a missing RIP");
});

test("a partial RIP still renders whatever exists", () => {
  const model = selectMobileHeroModel({ ...base, rip: { ...base.rip, rank: null, cohortSize: null } });
  assert.equal(model.rip.hasRip, true);
  assert.equal(model.rip.rankText, null);
  assert.equal(model.rip.tierText, "S Tier");
});

test("a missing logo degrades to the name alone", () => {
  const model = selectMobileHeroModel({ ...base, logoUrl: null });
  assert.equal(model.identity.hasLogo, false);
  assert.equal(model.identity.logoUrl, null);
  assert.equal(model.identity.name, "Perfect Order");
});

test("a missing name never renders an empty heading", () => {
  const model = selectMobileHeroModel({ ...base, setName: "   " });
  assert.equal(model.identity.name, "Selected Set");
});

test("a tier already carrying the word Tier is not doubled", () => {
  const model = selectMobileHeroModel({ ...base, rip: { ...base.rip, tier: "S Tier" } });
  assert.equal(model.rip.tierText, "S Tier");
});

// The page reads the summary as
// `setHeaderSummary?.setValue?.<key> ?? null`. These mirror that exactly, for
// each shape the summary can actually take mid-switch or on partial data.
function readLikeThePage(setHeaderSummary, rip = base.rip) {
  return selectMobileHeroModel({
    setName: "Perfect Order",
    era: "Mega Evolution",
    logoUrl: null,
    setValue: {
      current: setHeaderSummary?.setValue?.current ?? null,
      deltaAmount: setHeaderSummary?.setValue?.delta30dAmount ?? null,
      deltaPercent: setHeaderSummary?.setValue?.delta30dPercent ?? null,
      windowLabel: "30D",
    },
    rip,
  });
}

test("a summary that has not resolved yet renders the unavailable state, not $0.00", () => {
  for (const degraded of [undefined, null, {}, { setValue: undefined }, { setValue: {} }]) {
    const model = readLikeThePage(degraded);
    assert.equal(model.value.hasValue, false, `${JSON.stringify(degraded)} must not claim a value`);
    assert.equal(model.value.amountText, "—", "an unresolved summary shows the em dash, never a fabricated zero");
    assert.notEqual(model.value.amountText, "$0.00");
    assert.equal(model.value.deltaText, null);
    assert.equal(model.rip.hasRip, true, "RIP still renders while Set Value is unavailable");
  }
});

test("a real zero is still shown as a real zero", () => {
  // Only *missing* data degrades. An actual $0.00 must not be hidden.
  const model = readLikeThePage({ setValue: { current: 0, delta30dAmount: 0, delta30dPercent: 0 } });
  assert.equal(model.value.hasValue, true);
  assert.equal(model.value.amountText, "$0.00");
  assert.equal(model.value.direction, "neutral");
});

test("Set Value survives when RIP is the missing half", () => {
  const model = readLikeThePage(
    { setValue: { current: 42.5, delta30dAmount: null, delta30dPercent: null } },
    { label: "RIP Score", score: null, tier: null, rank: null, cohortSize: null, verdict: null }
  );
  assert.equal(model.value.hasValue, true);
  assert.equal(model.value.amountText, "$42.50");
  assert.equal(model.rip.hasRip, false);
  assert.equal(model.rip.isActionable, false);
});

test("the model is a pure function of its input", () => {
  // Parity: nothing about width, pointer or composition may reach these values.
  assert.deepEqual(selectMobileHeroModel(base), selectMobileHeroModel(base));
  assert.deepEqual(selectMobileHeroModel({}), selectMobileHeroModel(undefined));
});
