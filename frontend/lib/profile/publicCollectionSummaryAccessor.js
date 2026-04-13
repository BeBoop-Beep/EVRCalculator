// Server-only accessor that fetches from /api/public-profile/[username]/collection-summary. Not the route itself.
import "server-only";
import { getPublicCollectionByUsername } from "@/lib/profile/profileQueries";

/** @typedef {import("@/types/profile").PublicCollectionSummary} PublicCollectionSummary */

/** @param {unknown} value */
function toNullableFiniteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** @param {unknown} value */
function normalizeCollectionSummary(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const summary = /** @type {{
    portfolio_value?: unknown;
    cards_count?: unknown;
    sealed_count?: unknown;
    graded_count?: unknown;
    portfolio_delta_1d?: unknown;
    portfolio_delta_7d?: unknown;
    portfolio_delta_3m?: unknown;
    portfolio_delta_6m?: unknown;
    portfolio_delta_1y?: unknown;
    portfolio_delta_lifetime?: unknown;
    portfolio_delta_pct_1d?: unknown;
    portfolio_delta_pct_7d?: unknown;
    portfolio_delta_pct_3m?: unknown;
    portfolio_delta_pct_6m?: unknown;
    portfolio_delta_pct_1y?: unknown;
    portfolio_delta_pct_lifetime?: unknown;
  }} */ (value);

  return {
    portfolio_value: toNullableFiniteNumber(summary.portfolio_value),
    cards_count: toNullableFiniteNumber(summary.cards_count),
    sealed_count: toNullableFiniteNumber(summary.sealed_count),
    graded_count: toNullableFiniteNumber(summary.graded_count),
    portfolio_delta_1d: toNullableFiniteNumber(summary.portfolio_delta_1d),
    portfolio_delta_7d: toNullableFiniteNumber(summary.portfolio_delta_7d),
    portfolio_delta_3m: toNullableFiniteNumber(summary.portfolio_delta_3m),
    portfolio_delta_6m: toNullableFiniteNumber(summary.portfolio_delta_6m),
    portfolio_delta_1y: toNullableFiniteNumber(summary.portfolio_delta_1y),
    portfolio_delta_lifetime: toNullableFiniteNumber(summary.portfolio_delta_lifetime),
    portfolio_delta_pct_1d: toNullableFiniteNumber(summary.portfolio_delta_pct_1d),
    portfolio_delta_pct_7d: toNullableFiniteNumber(summary.portfolio_delta_pct_7d),
    portfolio_delta_pct_3m: toNullableFiniteNumber(summary.portfolio_delta_pct_3m),
    portfolio_delta_pct_6m: toNullableFiniteNumber(summary.portfolio_delta_pct_6m),
    portfolio_delta_pct_1y: toNullableFiniteNumber(summary.portfolio_delta_pct_1y),
    portfolio_delta_pct_lifetime: toNullableFiniteNumber(summary.portfolio_delta_pct_lifetime),
  };
}

/** @param {unknown} payload */
function extractCollectionSummary(payload) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return null;
  }

  const responseBody = /** @type {{ collection_summary?: unknown; summary?: unknown; data?: unknown; profile?: { collection_summary?: unknown } }} */ (payload);

  return normalizeCollectionSummary(
    responseBody.collection_summary
      ?? responseBody.summary
      ?? (responseBody.data && typeof responseBody.data === "object" && !Array.isArray(responseBody.data)
        ? /** @type {{ collection_summary?: unknown }} */ (responseBody.data).collection_summary ?? responseBody.data
        : null)
      ?? responseBody.profile?.collection_summary
  );
}

/**
 * @param {string} username
 * @returns {Promise<{ data: PublicCollectionSummary | null; warning: string | null }>}
 */
export async function getPublicCollectionSummaryByUsername(username) {
  const normalizedUsername = typeof username === "string" ? username.trim() : "";

  if (!normalizedUsername) {
    return {
      data: null,
      warning: "Collection summary request skipped: username is required.",
    };
  }

  const startedAt = Date.now();

  try {
    const response = await getPublicCollectionByUsername(normalizedUsername, {
      includeCollectionItems: false,
    });

    if (response.error) {
      return {
        data: null,
        warning: `Collection summary request failed for ${normalizedUsername}: ${response.error.status} ${response.error.message}`.trim(),
      };
    }

    const summary = extractCollectionSummary(response.data || {});

    if (!summary) {
      return {
        data: null,
        warning: `Collection summary response did not contain a valid summary for ${normalizedUsername}.`,
      };
    }

    return {
      data: summary,
      warning: null,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";

    return {
      data: null,
      warning: `Collection summary request failed for ${normalizedUsername}: ${message}`,
    };
  } finally {
    console.info("[publicCollectionSummaryAccessor] request_end", {
      username: normalizedUsername,
      pathUsed: "summary_snapshot",
      includeCollectionItems: false,
      elapsedMs: Date.now() - startedAt,
    });
  }
}