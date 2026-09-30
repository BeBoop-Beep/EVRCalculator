import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { bestOpenDetails } from "./productRankingsPresentation.mjs";

const read = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const lens = read("./RankingsProductLensClient.jsx");
const popover = read("./BestOpenDetailsPopover.jsx");
const info = read("../ui/InfoPopover.jsx");
const backend = fs.readFileSync(new URL("../../../backend/db/services/rankings_redesign_contract_service.py", import.meta.url), "utf8");
const pack = read("./SetPackMetrics.jsx");

test("absolute Product Overall is explicit and never converted into a benchmark", () => {
  assert.match(backend, /"scoreKind": "absolute", "scoreScale": "0-100"/);
  assert.match(backend, /"scoreValue": score_value/);
  assert.doesNotMatch(backend.slice(backend.indexOf("def project_product_contract"), backend.indexOf("def read_product_best_open_map")), /benchmark_presentation\(/);
  assert.match(lens, /row\.ripScore\?\.scoreValue/);
  assert.match(lens, /scoreKind === "benchmark"/);
  assert.doesNotMatch(lens, /scoreValue\s*\/\s*10|Math\.min\(10/);
});

test("persistent reference is outside sortable rows and reports pending publication", () => {
  assert.match(lens, /data-product-overall-reference/);
  assert.match(lens, /Benchmark not yet published/);
  assert.match(backend, /product_benchmark_publication_pending/);
  assert.ok(lens.indexOf("<ProductOverallReference") < lens.indexOf("<ScoresTable rows="));
});

test("Scores and Economics control is supplied to the actual table toolbar", () => {
  assert.match(lens, /toolbarControl=\{viewControl\}/);
  assert.match(lens, /ariaLabel="Product Rankings view"/);
});

test("Best-Open interpretation uses exact prices, signed differences, and a market denominator", () => {
  const above = bestOpenDetails({ bestOpenPrice: 80, bestOpenMarketPrice: 100, bestOpenSourceMarketDate: "2026-09-08", bestOpenMarketSourceDate: "2026-09-09" });
  assert.equal(above.differenceText, "+$20.00 · +20.0%");
  assert.match(above.interpretation, /market price is \$20\.00 above.*Best-Open threshold/);
  assert.notEqual(above.bestOpenDate, above.marketDate);
  const below = bestOpenDetails({ bestOpenPrice: 120, bestOpenMarketPrice: 100 });
  assert.equal(below.differenceText, "−$20.00 · −20.0%");
  assert.match(below.interpretation, /market price is \$20\.00 below.*Best-Open threshold/);
  assert.equal(bestOpenDetails({ bestOpenPrice: 10, bestOpenMarketPrice: 0 }).percentDifference, null);
});

test("one clean threshold and accessible popover are reused for Product and Set exact SKUs", () => {
  assert.doesNotMatch(lens, /bestOpenGap\(|below market|headroom/);
  assert.match(popover, /Best-Open details for/);
  assert.match(popover, /Current market/);
  assert.match(popover, /MSRP.*Unavailable/s);
  assert.match(info, /event\.key === "Escape"/);
  assert.match(info, /focus-visible:ring-2/);
  assert.match(pack, /<BestOpenDetailsPopover row=\{product\}/);
});

test("same-family SKU evidence stays independent", () => {
  const standard = bestOpenDetails({ familyKey: "elite_trainer_box", bestOpenPrice: 80, bestOpenMarketPrice: 100 });
  const center = bestOpenDetails({ familyKey: "elite_trainer_box", bestOpenPrice: 91, bestOpenMarketPrice: 120 });
  assert.notEqual(standard.threshold, center.threshold);
  assert.notEqual(standard.difference, center.difference);
});
