import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { selectChaseAccessibilityPresentation } from "../../explore/chaseAccessibilityPresentationSelector.mjs";
const rip = fs.readFileSync(new URL("./ProductRipSection.jsx", import.meta.url), "utf8");
const detail = fs.readFileSync(new URL("./SealedProductDetailClient.jsx", import.meta.url), "utf8");
test("Product RIP is Overall above three peer cards", () => {
  assert.ok(rip.indexOf('label="Overall RIP"') < rip.indexOf('data-three-pillar-summary="product"'));
  for (const label of ["Financial RIP", "Chase Accessibility", "Collector Appeal"]) assert.ok(rip.includes(label));
  assert.doesNotMatch(rip, /data-market-based-opening-quality/);
});
test("product and parent-set ownership labels remain truthful", () => {
  assert.match(rip, /This product/); assert.match(rip, /Parent set/); assert.match(rip, /Product RIP measures this product/);
});
test("Product Chase remains a separate Premium sibling", () => {
  assert.doesNotMatch(rip, /ProductChaseIntelligenceSection/); assert.match(detail, /<ProductRipSection detail=\{detail\}/); assert.match(detail, /<ProductChaseIntelligenceSection/);
});
test("Chase public score and set standing are used without a fabricated tier", () => {
  assert.match(rip, /chase\.publicScore/); assert.match(rip, /chase\.rank/); assert.match(rip, /chase\.cohortSize/); assert.doesNotMatch(rip, /chase\.tier/);
});
test("raw and model values cannot fill a missing public score", () => {
  const selected = selectChaseAccessibilityPresentation({ chaseAccessibility: { value: 0.001, percent: 0.1, modelScore: 40, status: "ready" } });
  assert.equal(selected.publicScore, null); assert.equal(selected.displayAccessibility, 0.1); assert.equal(selected.modelScore, 40);
});
test("Product RIP contains no public weighting recipe", () => { assert.doesNotMatch(rip, /0\.86|0\.04|86\/4\/10|90\/10 explanation/); });
