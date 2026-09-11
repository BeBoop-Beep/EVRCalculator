// Regression test for Task 6/7 of the 2026-09-10 rankings-entitlement-chase-density
// plan: STALE_INITIAL_BOOTSTRAP_CACHE.
//
// Fixture provenance (minimally redacted, from Task 6's diagnostic report,
// .superpowers/sdd/2026-09-10-rankings-entitlement-chase-density/task-6-report.md,
// Step 5 — "Actual SSR-rendered page props"):
//
//   - STALE_SEED below reproduces the byte-for-byte shape Task 6 captured on a
//     cold SSR hit for Ascended Heroes (target_id
//     75cd439d-aaa2-41cb-86f3-2fefa5b26e29): Overall/Financial/Collector fully
//     populated under overall_rip_v10_90_financial_v4_10_collector_appeal_v5,
//     but canonical.chaseAccessibility === {} and top-level
//     chaseAccessibilityPresentation === {} (a Next.js Data Cache entry that
//     predates this set's Chase Accessibility publication).
//   - RAW_FRESH_BACKEND_RESPONSE below reproduces Task 6 Step 2's raw
//     `GET /tcgs/pokemon/sets/me2pt5/rip/bootstrap` response (hit 12/12 times,
//     always identical): chaseAccessibilityPresentation.status === "ready"
//     under overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5.
//
// This test proves useSetRipBootstrapController's one-shot no-store
// reconciliation: given a seed with ready Overall/Financial/Collector but an
// empty Chase pillar, it must issue exactly ONE additional no-store fetch and,
// when that fetch comes back with a ready Chase pillar, replace the seed with
// it — without ever looping or polling.

// The hook under test uses the repo's "@/..." import alias
// (jsconfig.json's `paths: { "@/*": ["./*"] }`), which Next.js/webpack resolve
// at build time but which `tsx --test` does not resolve for a plain runtime
// require chain (unlike the source-string "contract" tests elsewhere in this
// repo, this test actually executes the hook, so the alias must resolve).
// This patches only this test process's CJS module resolution — no build
// config or other source file is touched.
import Module from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const projectRoot = fileURLToPath(new URL("../../", import.meta.url));
const originalResolveFilename = Module._resolveFilename;
Module._resolveFilename = function resolveAliasedFilename(request, ...rest) {
  if (typeof request === "string" && request.startsWith("@/")) {
    return originalResolveFilename.call(this, path.join(projectRoot, request.slice(2)), ...rest);
  }
  return originalResolveFilename.call(this, request, ...rest);
};

// NOTE: useSetRipBootstrapController.js must be loaded via dynamic import
// (below, inside the tests) rather than a static top-level import — ES module
// static imports are all linked/evaluated before any of this file's own
// top-level statements run, which would resolve the hook's "@/..." import
// before the Module._resolveFilename patch above is installed.
import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import TestRenderer, { act } from "react-test-renderer";

const { default: useSetRipBootstrapController } = await import("./useSetRipBootstrapController.js");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const SET_TARGET_ID = "75cd439d-aaa2-41cb-86f3-2fefa5b26e29";

// Task 6, Step 5, first (cold) SSR request — normalized initial-snapshot shape
// (this is exactly the `initialModuleSnapshots.ripBootstrapPayload` prop shape;
// pokemonSetRipBootstrapNormalizer.mjs's output keys are unchanged here).
const STALE_SEED = {
  contractVersion: "pokemon-set-rip-bootstrap-v1",
  available: true,
  set: { id: SET_TARGET_ID, canonical_key: "ascendedHeroes" },
  calculationRunId: "stale-pre-v12-run",
  marketDate: "2026-09-10",
  canonical: {
    overall: {
      rank: 14,
      tier: "B",
      score: 36.2055,
      version: "overall_rip_v10_90_financial_v4_10_collector_appeal_v5",
      absoluteScore: 36.2055,
      relativeScore: 57.21,
      rankedSetCount: 22,
      leaderNormalizedScore: 82.54,
    },
    financial: { score: 29.2179, leaderNormalizedScore: 71.69 },
    collector: { topSubjects: [] },
    chaseAccessibility: {},
  },
  canonicalSource: {
    publicRipContractV10: {},
    publicRipContractV11: { chaseAccessibility: {} },
  },
  chaseAccessibilityPresentation: {},
  summary: {},
  ripDecision: {},
  collectorSubjects: [],
  publicAnalyticsStatus: {},
  meta: {},
};

// Task 6, Step 2 — raw fresh backend response, run through the normalizer
// mentally (Step 4 proved the normalizer reproduces it unchanged in all three
// consumption points): canonical.chaseAccessibility === chaseAccessibilityPresentation,
// status "ready", under overall_rip_v12_86_....
const FRESH_CHASE_ACCESSIBILITY = {
  value: 0.000803020638883367,
  status: "ready",
  percent: 0.0803020638883367,
  setRank: 19,
  version: "chase_accessibility_v1_hc_value_squared_modeled_probability",
  cohortId: "1c68358bc47337581b31acd1fa5a4d536fdd12d4944107fbd5e72020f67648d2",
  chaseDepth: 3.95663914528006,
  marketDate: "2026-09-10",
  modelScore: 28.6484,
  publicScore: 38.73,
  mappedHcMass: 1,
  statusReason: null,
  setCohortSize: 22,
  publicQuestion: "How reachable are this set's most important cards from a pack?",
  calculationRunId: "464ee4cd-35f0-4ec7-82fa-bbaf76cbe6a9",
  technicalTooltip: "How accessible the set's most important collectible value is from one pack.",
};

// getPokemonSetRipBootstrap() (the client the reconciliation calls) fetches
// the RAW backend/proxy JSON and runs it through the real
// normalizePokemonSetRipBootstrap() (Task 6, Step 4, proved that normalizer
// faithful) — so the mocked fetch response must be the raw shape, matching
// Task 6, Step 2's actual `GET :8001/tcgs/pokemon/sets/me2pt5/rip/bootstrap`
// response (hit 12/12 times, always identical, "canonicalRip"/
// "chaseAccessibilityPresentation" top-level keys), not the normalized
// `canonical.*` shape used for the SSR seed above.
const RAW_FRESH_BACKEND_RESPONSE = {
  contractVersion: "pokemon-set-rip-bootstrap-v1",
  set: { id: SET_TARGET_ID, canonical_key: "ascendedHeroes" },
  calculationRunId: "464ee4cd-35f0-4ec7-82fa-bbaf76cbe6a9",
  marketDate: "2026-09-10",
  canonicalRip: {
    overall: {
      ...STALE_SEED.canonical.overall,
      score: 36.0835,
      version: "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5",
      absoluteScore: 36.0835,
      relativeScore: 52,
      leaderNormalizedScore: 80.23,
    },
    financial: { score: 29.1025, leaderNormalizedScore: 70.36 },
    collector: {},
  },
  collectorSubjects: [],
  chaseAccessibilityPresentation: FRESH_CHASE_ACCESSIBILITY,
  summary: {},
  ripDecision: {},
  publicAnalyticsStatus: {},
  meta: {},
};

function Harness({ setId, initialPayload, enabled, onResult }) {
  const result = useSetRipBootstrapController({ setId, initialPayload, enabled });
  onResult(result);
  return null;
}

function installFetchMock(responsePayload) {
  const calls = [];
  global.fetch = (url, options) => {
    calls.push({ url: String(url), options });
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(responsePayload),
    });
  };
  return calls;
}

async function flush(times = 4) {
  for (let i = 0; i < times; i += 1) {
    // eslint-disable-next-line no-await-in-loop
    await act(async () => {
      await wait(10);
    });
  }
}

test("STALE_INITIAL_BOOTSTRAP_CACHE: reproduces the bug — a stale empty-Chase seed with ready Overall/Financial/Collector is locked into state.success and never self-corrects without the fix", async () => {
  const originalFetch = global.fetch;
  let fetchCallCount = 0;
  global.fetch = (...args) => {
    fetchCallCount += 1;
    return Promise.reject(new Error("fetch should not be needed once a valid seed is accepted (pre-fix behavior)"));
  };

  let latest = null;
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(
      React.createElement(Harness, {
        setId: SET_TARGET_ID,
        initialPayload: STALE_SEED,
        enabled: true,
        onResult: (r) => { latest = r; },
      })
    );
  });

  // This is the exact defect Task 6 observed: state is "success" immediately,
  // and the Chase pillar is empty — the client has no idea it's stale.
  assert.equal(latest.state.status, "success");
  assert.deepEqual(latest.payload.canonical.chaseAccessibility, {});

  // Let the one-shot reconciliation attempt (which the fix always tries, since
  // this seed is core-ready-but-chase-missing) settle inside act() before this
  // test ends, so its rejection can't bleed into the next test's assertions.
  await flush(2);

  await act(async () => { renderer.unmount(); });
  global.fetch = originalFetch;
  void fetchCallCount;
});

test("Task 7 fix: performs exactly ONE no-store reconciliation fetch and replaces a stale empty-Chase seed once fresh Chase data is available", async () => {
  const calls = installFetchMock(RAW_FRESH_BACKEND_RESPONSE);

  let latest = null;
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(
      React.createElement(Harness, {
        setId: SET_TARGET_ID,
        initialPayload: STALE_SEED,
        enabled: true,
        onResult: (r) => { latest = r; },
      })
    );
  });

  // Immediately after mount, the stale seed is accepted as usual (unchanged
  // behavior for the fast path / other pillars).
  assert.equal(latest.state.status, "success");

  await flush();

  assert.equal(calls.length, 1, "expected exactly one reconciliation fetch, not zero and not a retry loop");
  assert.match(calls[0].url, /\/api\/tcgs\/pokemon\/sets\//);

  assert.equal(latest.state.status, "success");
  assert.equal(latest.payload.canonical.chaseAccessibility.status, "ready");
  assert.equal(
    latest.payload.canonical.overall.version,
    "overall_rip_v12_86_financial_v4_04_chase_accessibility_v1_10_collector_appeal_v5"
  );

  // Let further effects run — the fetch must not fire again (no polling, no
  // retry loop) now that Chase is ready.
  await flush();
  assert.equal(calls.length, 1, "reconciliation must never fire more than once per set view");

  await act(async () => { renderer.unmount(); });
  delete global.fetch;
});

test("Task 7 fix: when the reconciliation fetch still lacks Chase, the truthful Unavailable state is preserved and no further fetches are made", async () => {
  const stillStaleRawResponse = {
    ...RAW_FRESH_BACKEND_RESPONSE,
    chaseAccessibilityPresentation: {},
  };
  const calls = installFetchMock(stillStaleRawResponse);

  let latest = null;
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(
      React.createElement(Harness, {
        setId: SET_TARGET_ID,
        initialPayload: STALE_SEED,
        enabled: true,
        onResult: (r) => { latest = r; },
      })
    );
  });

  await flush();

  assert.equal(calls.length, 1, "expected exactly one reconciliation attempt even when Chase is still unpublished");
  assert.equal(latest.state.status, "success");
  assert.deepEqual(latest.payload.canonical.chaseAccessibility, {}, "Unavailable must remain truthful, not silently faked as ready");

  await flush();
  assert.equal(calls.length, 1, "must not retry or poll when the backend genuinely still lacks Chase");

  await act(async () => { renderer.unmount(); });
  delete global.fetch;
});

test("Final fix wave: the reconciliation fetch fires for a non-entitled/anonymous viewer too, since Chase Accessibility is rendered ungated on the live page", async () => {
  // RipDecisionPage renders <ChaseAccessibilitySnapshotCard> inside the public
  // data-three-pillar-summary row, outside any canViewProductRipIntelligence
  // gate — so Chase Accessibility is actually a public pillar. Gating the
  // one-shot repair fetch on entitlement (as an earlier fix round did) would
  // leave exactly the viewers who can see the card stuck on a stale
  // "Unavailable" forever. The hook no longer accepts or checks an `entitled`
  // flag: the fetch is bounded solely by the other 3 conditions (valid seed,
  // Overall/Financial/Collector ready, Chase missing) and fires once per set
  // view regardless of viewer entitlement.
  const calls = installFetchMock(RAW_FRESH_BACKEND_RESPONSE);

  let latest = null;
  let renderer;
  await act(async () => {
    renderer = TestRenderer.create(
      React.createElement(Harness, {
        setId: SET_TARGET_ID,
        initialPayload: STALE_SEED,
        enabled: true,
        onResult: (r) => { latest = r; },
      })
    );
  });

  assert.equal(latest.state.status, "success");

  await flush();

  assert.equal(calls.length, 1, "a non-entitled/anonymous viewer must still trigger the one-shot reconciliation fetch when the seed is core-ready-but-chase-missing");
  assert.equal(latest.state.status, "success");
  assert.equal(latest.payload.canonical.chaseAccessibility.status, "ready", "the fresh Chase data must replace the stale seed for this viewer too");

  await flush();
  assert.equal(calls.length, 1, "reconciliation must never fire more than once per set view");

  await act(async () => { renderer.unmount(); });
  delete global.fetch;
});
