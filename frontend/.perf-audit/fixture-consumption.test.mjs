import assert from "node:assert/strict";
import test from "node:test";
import { createFixtureConsumption } from "./fixture-consumption.mjs";

test("preflight does not satisfy browser critical-fixture consumption", () => {
  const tracker = createFixtureConsumption({ routes: { "/critical": { critical: true } } });
  tracker.record("/critical", { phase: "preflight" });
  assert.deepEqual(tracker.report().unusedBrowserCriticalFixtures, ["/critical"]);
  assert.deepEqual(tracker.report().browserRequests, []);
});

test("browser traffic alone satisfies critical consumption", () => {
  const tracker = createFixtureConsumption({ routes: { "/critical": { critical: true } } });
  tracker.record("/critical", { phase: "preflight" });
  tracker.record("/critical", { phase: "browser" });
  assert.deepEqual(tracker.report().unusedBrowserCriticalFixtures, []);
  assert.deepEqual(tracker.report().browserRequests, [{ route: "/critical", count: 1 }]);
});

test("unexpected traffic is classified by phase", () => {
  const tracker = createFixtureConsumption({ routes: {} });
  tracker.record("/missing-a", { phase: "preflight", expected: false, method: "HEAD" });
  tracker.record("/missing-b", { expected: false });
  const report = tracker.report();
  assert.deepEqual(report.unexpectedPreflightRequests, ["HEAD /missing-a"]);
  assert.deepEqual(report.unexpectedBrowserRequests, ["GET /missing-b"]);
});

test("browser accounting can reset per mounted case without erasing preflight", () => {
  const tracker = createFixtureConsumption({ routes: { "/critical": { critical: true } } });
  tracker.record("/critical", { phase: "preflight" });
  tracker.record("/critical");
  tracker.resetBrowser();
  assert.equal(tracker.report().preflightRequests.length, 1);
  assert.deepEqual(tracker.report().browserRequests, []);
  assert.deepEqual(tracker.report().unusedBrowserCriticalFixtures, ["/critical"]);
});
