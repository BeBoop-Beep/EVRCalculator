import { cache } from "react";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

/**
 * Server-side read of the published global + era opening economics.
 *
 * The heavy work — pooling 22,000,000 exact simulated outcomes into equal-set
 * weighted quantiles — happens once per day inside the canonical RIP Stats
 * publication. This only transports the finished scalars, so the payload is a
 * few hundred bytes per scope and no simulation array is ever serialized into
 * the RSC flight payload.
 *
 * Failure NEVER throws. Overall and Eras must be able to go unavailable on
 * their own without taking the Sets or Products lenses down with them, so a
 * failed fetch resolves to the same explicit unavailable contract the backend
 * itself returns.
 */

const BACKEND_URL = getBackendApiBaseUrl();
const REVALIDATE_SECONDS = 120;
const V3_CONTRACT = "pokemon-rip-stats-v3";
const V3_METHODOLOGY = "hierarchical_product_per_pack_empirical_v1";
const V3_WEIGHTING = "equal-set_equal-family_equal-sku-v1";
const V3_BASIS = "all_modeled_products_per_pack_equivalent";

function unavailable(reason) {
  return { status: "unavailable", reason, contractVersion: V3_CONTRACT, basis: V3_BASIS,
    methodology: { version: V3_METHODOLOGY, weightingVersion: V3_WEIGHTING },
    global: null, eras: [], sets: [], familyBenchmarks: [] };
}

export function isOpeningEconomicsV3(payload) {
  return Boolean(payload && payload.status === "available" && payload.global
    && payload.contractVersion === V3_CONTRACT && payload.basis === V3_BASIS
    && payload.methodology?.version === V3_METHODOLOGY
    && payload.methodology?.weightingVersion === V3_WEIGHTING);
}

async function fetchOpeningEconomics() {
  try {
    const response = await fetch(`${BACKEND_URL}/explore/opening-economics`, {
      next: { revalidate: REVALIDATE_SECONDS },
    });
    if (!response.ok) {
      return unavailable("request_failed");
    }
    const payload = await response.json();
    if (!payload || typeof payload !== "object") {
      return unavailable("malformed_response");
    }
    // The backend is the only authority on availability. A payload that says
    // "available" without a global scope is treated as unavailable rather than
    // rendered with blank tiles.
    if (isOpeningEconomicsV3(payload)) {
      return payload;
    }
    return unavailable(payload.status === "available"
      ? "incompatible_opening_economics_contract"
      : payload.reason || "opening_economics_unavailable");
  } catch {
    return unavailable("request_failed");
  }
}

export const getOpeningEconomics = cache(fetchOpeningEconomics);
