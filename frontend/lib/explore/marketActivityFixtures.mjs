export const MARKET_ACTIVITY_CONTRACT_VERSION = "market_activity_v1.1";
export const MARKET_ACTIVITY_FIXTURE_VERSION = "market_activity_v1_fixtures_2";
export const MARKET_ACTIVITY_MANIFEST_SHA256 = "e6235d9c73dc7ce6e38b81431bcfe60e4a32ae27f2780632aae45d407705e007";

const canonicalize = (value) => {
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalize(value[key])}`).join(",")}}`;
  return JSON.stringify(value);
};

async function sha256(value) {
  const bytes = new TextEncoder().encode(canonicalize(value));
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

const fixtureLoaders = Object.freeze({
  fma_fixture_01: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_01_fresh_complete.json"),
  fma_fixture_02: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_02_partial_sales.json"),
  fma_fixture_03: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_03_stale_asks.json"),
  fma_fixture_04: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_04_zero_with_proof.json"),
  fma_fixture_05: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_05_not_collected.json"),
  fma_fixture_06: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_06_missing_grade.json"),
  fma_fixture_07: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_07_insufficient_peers.json"),
  fma_fixture_08: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_08_unsupported_asset.json"),
  fma_fixture_09: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_09_generation_mismatch.json"),
  fma_fixture_10: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_10_constituent_page.json"),
  fma_fixture_11: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_11_group_activity.json"),
  fma_fixture_12: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_12_legacy_no_receipts.json"),
  fma_fixture_13: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_13_future_right_edge.json"),
  fma_fixture_14: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_14_mixed_unconfirmed_asks.json"),
  fma_fixture_15: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_15_multi_date_series.json"),
  fma_fixture_16: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_16_constituent_page_cursor.json"),
  fma_fixture_17: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_17_cursor_mismatch.json"),
  fma_fixture_18: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_18_activity_generation_expired.json"),
  fma_fixture_19: () => import("../../../docs/research/market_activity_v1/fixtures/fma_fixture_19_group_roster_101.json"),
});

export const MARKET_ACTIVITY_FIXTURE_IDS = Object.freeze(Object.keys(fixtureLoaders));

export function validateActivityFixture(payload) {
  if (!payload || payload.contractVersion !== MARKET_ACTIVITY_CONTRACT_VERSION) throw new Error("Activity fixture contract version mismatch.");
  if (!payload.request?.marketKey || !payload.request?.activityGenerationId || !payload.request?.rosterRef || !payload.request?.asOf || !payload.request?.windowDays) {
    throw new Error("Activity fixture is missing an exact request scope pin.");
  }
  if (!Object.prototype.hasOwnProperty.call(payload, "evidenceFingerprint")) throw new Error("Activity fixture is missing its evidence fingerprint.");
  return payload;
}

/** Fixture-only adapter. FMA-4 replaces this seam with the authenticated POST transport. */
export async function loadMarketActivityFixture({ fixtureId = "fma_fixture_11", signal } = {}) {
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  const loader = fixtureLoaders[fixtureId];
  if (!loader) throw new Error(`Unknown Market Activity fixture: ${fixtureId}`);
  const [module, manifestModule] = await Promise.all([loader(), import("../../../docs/research/market_activity_v1/fixtures/manifest.json")]);
  if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
  const manifest = manifestModule.default || manifestModule;
  if (manifest.contractVersion !== MARKET_ACTIVITY_CONTRACT_VERSION || manifest.manifestVersion !== MARKET_ACTIVITY_FIXTURE_VERSION
    || await sha256(manifest) !== MARKET_ACTIVITY_MANIFEST_SHA256) throw new Error("Market Activity fixture manifest identity mismatch.");
  const record = manifest.fixtures.find((entry) => entry.fixtureId === fixtureId);
  const payload = module.default || module;
  if (!record || await sha256(payload) !== record.sha256) throw new Error("Market Activity fixture fingerprint mismatch.");
  return validateActivityFixture(payload.expected);
}
