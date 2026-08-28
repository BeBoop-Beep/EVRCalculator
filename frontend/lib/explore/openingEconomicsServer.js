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

function unavailable(reason) {
  return { status: "unavailable", reason, global: null, eras: [] };
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
    if (payload.status === "available" && payload.global) {
      return payload;
    }
    return unavailable(payload.reason || "opening_economics_unavailable");
  } catch {
    return unavailable("request_failed");
  }
}

export const getOpeningEconomics = cache(fetchOpeningEconomics);
