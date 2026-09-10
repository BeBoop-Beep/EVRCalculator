import "../../test-support/renderComponentRegister.mjs";

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import TestRenderer from "react-test-renderer";

// Mock modules
const mockExploreTableClientCalls = [];
const mockUseRankingsAccess = {
  returnValue: {
    canViewRankingsIntelligence: false,
    canViewCardChaseEfficiency: false,
    authStatus: "anonymous",
    requestKey: "anon-1",
  },
};

// Create a mock that captures calls
const mockExploreTableClient = React.forwardRef(function MockExploreTableClient(props) {
  mockExploreTableClientCalls.push(props);
  return null;
});

// Patch the modules before importing the component
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// We'll need to use a different approach since we can't easily mock ES modules in node:test
// Let's use a static analysis approach instead, matching the existing test patterns
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.join(here, "RankingsLazyClient.jsx"), "utf8").replace(/\r\n/g, "\n");

test("passes the real entitlement flag to ExploreTableClient, not a hardcoded true", () => {
  // Line 278 should have canViewProductRipIntelligence={canViewRankingsIntelligence}
  // not canViewProductRipIntelligence with no value (which is JSX shorthand for true)
  assert.match(source, /canViewProductRipIntelligence=\{canViewRankingsIntelligence\}/);

  // Verify it doesn't have the bare JSX shorthand anymore
  const lines = source.split("\n");
  const exploreTableClientLines = lines.filter((line, idx) =>
    line.includes("ExploreTableClient") && line.includes("eraFilter={selectedEra}")
  );

  // Make sure we found the line
  assert.ok(exploreTableClientLines.length > 0, "ExploreTableClient render call not found");

  // Verify the problematic pattern is gone
  const hasBareProp = exploreTableClientLines.some(line =>
    /canViewProductRipIntelligence\s+eraFilter/.test(line)
  );
  assert.ok(!hasBareProp, "ExploreTableClient still has bare canViewProductRipIntelligence prop (JSX shorthand for true)");
});
