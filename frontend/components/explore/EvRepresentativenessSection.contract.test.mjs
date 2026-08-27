import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const component = fs.readFileSync(new URL("./simulation-evidence/EvRepresentativenessSection.jsx", import.meta.url), "utf8");
const page = fs.readFileSync(new URL("./RipDecisionPage.jsx", import.meta.url), "utf8");
const article = fs.readFileSync(new URL("../articles/EvResearchLiveExamples.jsx", import.meta.url), "utf8");
const styles = fs.readFileSync(new URL("./RipDecisionPage.module.css", import.meta.url), "utf8");

test("one shared EV convergence implementation serves the set deep dive and article", () => {
  assert.ok(page.includes('import EvRepresentativenessSection from "./simulation-evidence/EvRepresentativenessSection.jsx"'));
  assert.ok(article.includes('import EvRepresentativenessSection from "@/components/explore/simulation-evidence/EvRepresentativenessSection.jsx"'));
  assert.ok(component.includes("selectEvRepresentativenessPublicV1"));
});

test("deep research starts with convergence evidence rather than the primary EV comparison", () => {
  for (const phrase of ["When Does EV Start Looking Real?", "real-sized opening runs", "Reach 80% of EV Reliably", "One-sided threshold", "Converge Near EV", "Two-sided convergence", "Chance to Reach at Least 80% of EV"]) assert.ok(component.includes(phrase), phrase);
  assert.equal(component.includes("Typical pack (P50)"), false);
  assert.equal(component.includes("Long-run EV\", ev"), false);
  assert.ok(component.includes('role="table"'));
  assert.ok(component.includes("<InfoPopover"));
});

test("realistic opening size is selected from dynamic product metadata", () => {
  assert.ok(component.includes("product?.packCount"));
  assert.ok(component.includes("product.productName"));
  assert.equal(component.includes("36 packs"), false);
  assert.ok(styles.includes(".evMilestones { grid-template-columns: 1fr; }"));
});
