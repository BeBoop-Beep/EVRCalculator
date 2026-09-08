import test from "node:test";
import assert from "node:assert/strict";
import { describeRelativePerformance } from "./marketExplorerComparison.mjs";

test("relative performance names the timeframe, both returns, and percentage-point spread", () => {
  assert.equal(
    describeRelativePerformance("7D", "All Dragonite Cards", 4.1, "Dragonite + Arceus", 1.6),
    "Over 7D, All Dragonite Cards returned 4.1%, versus 1.6% for Dragonite + Arceus â€” a 2.5 percentage-point difference.",
  );
});
