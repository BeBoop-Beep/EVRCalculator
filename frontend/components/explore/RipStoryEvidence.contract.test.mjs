import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const source = fs.readFileSync(
  path.join(
    path.dirname(fileURLToPath(import.meta.url)),
    "RipStoryEvidence.jsx",
  ),
  "utf8",
);

test("demand share leads with its value and keeps the definition popover", () => {
  const value = source.indexOf("data-demand-share-value");
  const label = source.indexOf("data-demand-share-label");
  assert.ok(
    value >= 0 && label > value,
    "percentage is presented before its definition",
  );
  assert.ok(source.slice(label).includes("Set Demand"));
  assert.ok(source.slice(label).includes("<InfoPopover"));
  assert.ok(
    source.includes("text-xl font-semibold"),
    "share is the primary typographic value",
  );
  assert.ok(
    source.includes("subject.demandShareLabel"),
    "validated selector output remains the source",
  );
});

test("desirable subjects remain visible while acquisition counts follow Index Plus access", () => {
  assert.ok(
    source.includes(
      "Most Desirable Pokémon data is not available for this set yet.",
    ),
  );
  assert.ok(source.includes("SubjectAcquisition"));
  assert.ok(
    source.includes(
      'data-subject-acquisition={canViewAdvanced ? "available" : "locked"}',
    ),
  );
  assert.ok(source.includes("packsFor50PercentChance"));
  assert.ok(source.includes("packsFor90PercentChance"));
  assert.ok(source.includes("canViewAdvanced && value"));
  assert.ok(source.includes("Index Plus"));
});
