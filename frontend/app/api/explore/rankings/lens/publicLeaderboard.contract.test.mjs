import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

// The register hook resolves the `@/` alias the route imports.
import "../../../../../test-support/renderComponentRegister.mjs";

const route = fs.readFileSync(new URL("./route.js", import.meta.url), "utf8");
const lazy = fs.readFileSync(new URL("../../../../../components/explore/RankingsLazyClient.jsx", import.meta.url), "utf8");

const { GET } = await import("./route.js");

test("Set lens applies the entitlement-aware Set Rankings projection", () => {
  const sets = route.slice(route.indexOf('if (lens === "sets")'), route.indexOf('if (lens === "eras")'));
  assert.match(sets, /projectSetRankingsLensTargets\(rankTargets\(eligible\), payload\?\.access\)/);
  assert.doesNotMatch(sets, /canViewRankingsIntelligence:/);
});

test("Era lens returns the prepared public contract without an entitlement lock", () => {
  const eras = route.slice(route.indexOf('if (lens === "eras")'), route.indexOf('if (lens === "products")'));
  assert.match(eras, /status: "available"/);
  assert.match(eras, /eraSetStrength/);
  assert.doesNotMatch(eras, /status: "locked"|rankingsIntelligence !== true/);

  const loader = lazy.slice(lazy.indexOf("const loadEra"), lazy.indexOf("const loadSets"));
  assert.doesNotMatch(loader, /canViewRankingsIntelligence|authStatus !== "resolved"/);
});

test("Product and Card entitlement branches remain present", () => {
  assert.match(route, /if \(lens === "products"\)/);
  assert.match(lazy, /if \(!canViewCardChaseEfficiency\) return Promise\.resolve\(null\)/);
});

// The three tests above are source-string checks: they prove the route CALLS
// projectSetRankingsLensTargets, but not that the projection actually reaches
// the wire for an anonymous caller. This test closes that gap end-to-end: it
// stubs the backend fetch the route makes with a fixture target carrying
// paid evidence in exactly the leaves Task 2's PUBLIC_BLOCK_LEAVES excludes,
// invokes the real `GET` with no Authorization/Cookie header, and asserts
// the serialized JSON response never contains those leaves.

const PAID_FIXTURE_SCORE = 87.3;

function captureBackend(response) {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return response;
  };
  return { calls, restore: () => { globalThis.fetch = originalFetch; } };
}

const backendResponse = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

function anonymousLensRequest(searchParams) {
  return {
    headers: { get: () => null },
    nextUrl: new URL(`http://localhost/api/explore/rankings/lens?${searchParams}`),
  };
}

const paidFixtureTarget = {
  target_type: "set",
  target_id: "ascended",
  name: "Ascended Heroes",
  era: "Scarlet & Violet",
  setRipV1: {
    score: PAID_FIXTURE_SCORE,
    modelScore: PAID_FIXTURE_SCORE,
    leaderNormalizedScore: PAID_FIXTURE_SCORE,
    publicScore: 38.37,
    tier: "C",
    rank: 4,
    cohortSize: 22,
    rankable: true,
    methodologyVersion: "v1",
    familyScores: { flagship: PAID_FIXTURE_SCORE },
    displayFamilyScores: { flagship: PAID_FIXTURE_SCORE },
    participatingFamilyCount: 3,
    participatingFamilies: ["flagship"],
    skuEvidenceCount: 12,
    chaseAccessibility: {
      value: 0.0037,
      modelScore: PAID_FIXTURE_SCORE,
      publicScore: 38.37,
      status: "ready",
    },
  },
  chaseAccessibility: {
    value: 0.0037,
    modelScore: PAID_FIXTURE_SCORE,
    publicScore: 38.37,
    status: "ready",
  },
};

test("anonymous rankings lens response for sets contains no paid fixture values", async () => {
  const backend = captureBackend(
    backendResponse(200, {
      targets: [paidFixtureTarget],
      access: { rankingsIntelligence: false, requiredPlan: "plus" },
      meta: { comparisonSnapshots: { currentMarketDate: "2026-09-09" } },
    }),
  );
  try {
    const response = await GET(anonymousLensRequest("lens=sets"));
    const body = await response.json();

    assert.equal(backend.calls.length, 1, "the route must call the backend lens endpoint exactly once");
    assert.equal(backend.calls[0].init.headers.Authorization, undefined,
      "an anonymous request must never forge a credential toward the backend");
    assert.equal(backend.calls[0].init.headers.Cookie, undefined);

    const serialized = JSON.stringify(body);
    assert.doesNotMatch(serialized, /familyScores/);
    assert.doesNotMatch(serialized, /displayFamilyScores/);
    assert.doesNotMatch(serialized, /chaseAccessibility/);
    assert.doesNotMatch(serialized, /participatingFamilyCount/);
    assert.doesNotMatch(serialized, /participatingFamilies/);
    assert.doesNotMatch(serialized, /skuEvidenceCount/);
    assert.equal(serialized.includes(String(PAID_FIXTURE_SCORE)), false,
      "the paid fixture score must not leak through any surviving leaf");

    // Meaningful, not vacuous: the public leaves the anonymous contract does
    // allow must still be present.
    assert.equal(body.targets[0].setRipV1.publicScore, 38.37);
    assert.equal(body.targets[0].setRipV1.rank, 4);
  } finally {
    backend.restore();
  }
});
