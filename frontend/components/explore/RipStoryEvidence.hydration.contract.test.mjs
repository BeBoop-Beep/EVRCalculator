import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const evidence = fs.readFileSync(path.resolve("components/explore/RipStoryEvidence.jsx"), "utf8");
const decision = fs.readFileSync(path.resolve("components/explore/RipDecisionPage.jsx"), "utf8");

test("desktop demand-share label uses a div wrapper around InfoPopover", () => {
  assert.match(evidence, /<div\s+data-demand-share-label[\s\S]*?<InfoPopover[\s\S]*?<\/div>/);
  assert.doesNotMatch(evidence, /<p\s+data-demand-share-label[\s\S]*?<InfoPopover[\s\S]*?<\/p>/);
});

test("Best Way family-rank InfoPopover is not nested in an inline span", () => {
  const infoIndex = decision.indexOf("Ranked against all currently eligible modeled");
  assert.ok(infoIndex >= 0);
  assert.ok(
    decision.lastIndexOf("<div className={styles.heroBadge}>", infoIndex) >
      decision.lastIndexOf("<span className={styles.heroBadge}>", infoIndex),
    "the nearest family-rank badge wrapper must be a div",
  );
});
