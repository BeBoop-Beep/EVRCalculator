// .jsx on purpose: the module under test imports a CJS-ambiguous .js route helper, which only resolves through the transformed (CJS) loader path.
import test from "node:test";
import assert from "node:assert/strict";
import {
  buildConstituentPreviewModel,
  positionConstituentPreview,
  resolveConstituentDetailHref,
  resolveConstituentImage,
} from "./marketExplorerConstituentPresentation.mjs";
import { toGrayscaleColor } from "./marketExplorerFocusColor.mjs";

// --- image resolver ----------------------------------------------------------
test("image resolver: small only", () => {
  const image = resolveConstituentImage({ imageSmallUrl: "s.png" });
  assert.deepEqual(image, { hasImage: true, thumbUrl: "s.png", previewUrl: "s.png" });
});
test("image resolver: standard only", () => {
  const image = resolveConstituentImage({ imageUrl: "m.png" });
  assert.deepEqual(image, { hasImage: true, thumbUrl: "m.png", previewUrl: "m.png" });
});
test("image resolver: large only (thumb falls back, preview uses it)", () => {
  const image = resolveConstituentImage({ imageLargeUrl: "l.png" });
  assert.deepEqual(image, { hasImage: true, thumbUrl: "l.png", previewUrl: "l.png" });
});
test("image resolver: all three -> thumb prefers small, preview prefers large", () => {
  const image = resolveConstituentImage({ imageSmallUrl: "s.png", imageUrl: "m.png", imageLargeUrl: "l.png" });
  assert.equal(image.thumbUrl, "s.png");
  assert.equal(image.previewUrl, "l.png");
});
test("image resolver: none / blank / non-string -> deliberate no-image result", () => {
  for (const row of [{}, null, undefined, { imageUrl: "  " }, { imageSmallUrl: 5 }]) {
    assert.deepEqual(resolveConstituentImage(row), { hasImage: false, thumbUrl: null, previewUrl: null });
  }
});
test("image resolver is row-driven: it never reads labels", () => {
  assert.equal(resolveConstituentImage({ cardName: "Fossil", setName: "Fossil", rarity: "Rare Ultra" }).hasImage, false);
});

// --- detail route ------------------------------------------------------------
test("detail href: card rows use the stable card route with the variant", () => {
  const href = resolveConstituentDetailHref({ canonicalCardId: "card-1", cardVariantId: "var-9", setName: "Fossil", setId: "set-1" });
  assert.equal(href, "/TCGs/Pokemon/Sets/fossil/Cards/card-1?variant=var-9");
});
test("detail href: sealed rows use the stable sealed product route", () => {
  assert.equal(resolveConstituentDetailHref({ sealedProductId: "prod 7", setName: "X" }), "/sealed-products/prod%207");
});
test("detail href: missing identity yields null, never a broken link", () => {
  assert.equal(resolveConstituentDetailHref({ cardName: "Fossil", setName: "Fossil" }), null);
  assert.equal(resolveConstituentDetailHref({ canonicalCardId: "c1" }), null, "no set identity");
  assert.equal(resolveConstituentDetailHref({ rank: 3 }), null);
  assert.equal(resolveConstituentDetailHref(null), null);
  assert.equal(resolveConstituentDetailHref({ sealedProductId: "  " }), null);
});

// --- preview model -----------------------------------------------------------
test("preview model (card): name, set, price, rarity, edition, printing; no raw dump", () => {
  const model = buildConstituentPreviewModel(
    { cardName: "Charizard", setName: "Base Set", marketPrice: 500, rarity: "Rare Holo", edition: "1st-edition", printingType: "holo", secretField: "x", imageLargeUrl: "l.png" },
    { asset: "cards", formatPrice: (v) => `$${v}` });
  assert.equal(model.kind, "card");
  assert.equal(model.title, "Charizard");
  assert.equal(model.image.previewUrl, "l.png");
  const labels = model.fields.map((f) => f.label);
  assert.deepEqual(labels, ["Set", "Market price", "Rarity", "Edition", "Printing"]);
  assert.ok(!JSON.stringify(model).includes("secretField"));
  assert.equal(model.fields.find((f) => f.label === "Market price").value, "$500");
});
test("preview model (sealed): product, set, price, family, variant; empty fields omitted", () => {
  const model = buildConstituentPreviewModel({ productName: "ETB", setName: "S", marketPrice: 50, productFamilyLabel: "Elite Trainer Box" }, { asset: "sealed" });
  assert.equal(model.kind, "sealed");
  assert.deepEqual(model.fields.map((f) => f.label), ["Set", "Market price", "Product family"]);
});

// --- positioning -------------------------------------------------------------
test("preview placement: right by default, flips left near the right edge, clamps vertically", () => {
  const viewport = { width: 1000, height: 800 };
  const size = { width: 232, height: 340 };
  const right = positionConstituentPreview({ left: 100, right: 130, top: 300, bottom: 340 }, size, viewport);
  assert.equal(right.placement, "right");
  const left = positionConstituentPreview({ left: 900, right: 930, top: 300, bottom: 340 }, size, viewport);
  assert.equal(left.placement, "left");
  assert.ok(left.left + left.width <= viewport.width - 8);
  const low = positionConstituentPreview({ left: 100, right: 130, top: 780, bottom: 800 }, size, viewport);
  assert.ok(low.top + 340 <= viewport.height - 8);
  const tiny = positionConstituentPreview({ left: 10, right: 40, top: 10, bottom: 50 }, size, { width: 300, height: 200 });
  assert.ok(tiny.maxHeight <= 200 - 16, "never taller than the viewport");
});

// --- focus colour ------------------------------------------------------------
test("grayscale: hex and rgb collapse to neutral grey, unknown falls back", () => {
  for (const color of ["#ff0000", "#0af", "rgb(20, 200, 40)", "rgba(20,200,40,0.5)"]) {
    const match = toGrayscaleColor(color).match(/^rgb\((\d+),(\d+),(\d+)\)$/);
    assert.ok(match && match[1] === match[2] && match[2] === match[3], color);
  }
  assert.equal(toGrayscaleColor("hsl(10 50% 50%)"), "rgb(148,163,184)");
  assert.equal(toGrayscaleColor(undefined), "rgb(148,163,184)");
});
