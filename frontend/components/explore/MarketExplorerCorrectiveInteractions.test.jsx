import "../../test-support/renderComponentRegister.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

import MarketExplorerDetails from "./MarketExplorerDetails.jsx";
import { buildExplorerChartModel } from "@/lib/explore/marketExplorerSeries.mjs";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const parent = (key, label, constituentCount) => ({
  key,
  label,
  isParent: true,
  available: true,
  availability: "available",
  compositionKind: "index_and_composition",
  constituentCount,
  color: "#22d3ee",
  changes: {},
  familyChanges: {},
});

test("V2 Raw and Total Sealed parents expose Inspect from composition capability", () => {
  const inspected = [];
  let renderer;
  act(() => {
    renderer = TestRenderer.create(
      <MarketExplorerDetails
        series={[
          parent("raw", "Raw Card Market", 20316),
          parent("sealedMarket", "Total Sealed Market", 1374),
        ]}
        activeSeriesId="raw"
        onInspect={(key) => inspected.push(key)}
      />,
    );
  });
  const raw = renderer.root.findByProps({ "data-market-explorer-inspect": "raw" });
  const sealed = renderer.root.findByProps({ "data-market-explorer-inspect": "sealedMarket" });
  assert.equal(raw.props.children, "Inspecting");
  assert.equal(sealed.props.children, "Inspect");
  act(() => sealed.props.onClick());
  assert.deepEqual(inspected, ["sealedMarket"]);
});

test("the constituent LT selector is intrinsically sized with no forced trailing region", () => {
  const source = fs.readFileSync(new URL("./MarketExplorerConstituents.jsx", import.meta.url), "utf8");
  assert.match(source, /data-market-constituents-window-selector[\s\S]*?inline-flex w-fit max-w-full/);
  assert.match(source, /className="ml-auto w-fit max-w-full text-right"/);
  assert.doesNotMatch(source, /sm:min-w-\[16rem\]/);
});

test("1Y with less than 365 days starts at the earliest real observation and fills its domain", () => {
  const series = [{
    key: "raw",
    label: "Raw Card Market",
    marketType: "parent",
    available: true,
    color: "#22d3ee",
    comparisonAsOf: "2026-10-01",
    trend: [
      { date: "2026-06-01", value: 100 },
      { date: "2026-08-01", value: 103 },
      { date: "2026-10-01", value: 105 },
    ],
    familyChanges: { "1Y": { available: false } },
  }];
  const model = buildExplorerChartModel({}, series, "1Y");
  assert.equal(model.startDate, "2026-06-01");
  assert.equal(model.endDate, "2026-10-01");
  assert.deepEqual(model.series[0].values.filter(Number.isFinite), [100, 103, 105]);
});
