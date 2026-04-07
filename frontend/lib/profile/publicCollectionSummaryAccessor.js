// Server-only accessor that fetches from /api/public-profile/[username]/collection-summary. Not the route itself.
import "server-only";
import { headers } from "next/headers";

/** @typedef {import("@/types/profile").PublicCollectionSummary} PublicCollectionSummary */

/** @param {unknown} value */
function toNullableFiniteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** @param {string} username */
function getPublicCollectionSummaryEndpointPath(username) {
  return `/api/public-profile/${encodeURIComponent(username)}/collection-summary`;
}

/** @param {string} username */
async function buildPublicCollectionSummaryUrl(username) {
  const endpointPath = getPublicCollectionSummaryEndpointPath(username);

  try {
    const requestHeaders = await headers();
    const host = requestHeaders.get("x-forwarded-host") || requestHeaders.get("host");

    if (host) {
      const protocolHint = requestHeaders.get("x-forwarded-proto");
      const protocol = protocolHint || (host.includes("localhost") || host.startsWith("127.0.0.1") ? "http" : "https");
      return `${protocol}://${host}${endpointPath}`;
    }
  } catch {
    // Continue to fallback resolution when not in a request-bound context.
  }

  const fallbackBaseUrl = process.env.NEXT_PUBLIC_BASE_URL
    || process.env.NEXT_PUBLIC_API_URL
    || "http://localhost:3000";
  const baseUrl = fallbackBaseUrl.endsWith("/") ? fallbackBaseUrl : `${fallbackBaseUrl}/`;

  return new URL(endpointPath.slice(1), baseUrl).toString();
}

/** @param {unknown} value */
function normalizeCollectionSummary(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const summary = /** @type {{ portfolio_value?: unknown; cards_count?: unknown; sealed_count?: unknown; graded_count?: unknown }} */ (value);

  return {
    portfolio_value: toNullableFiniteNumber(summary.portfolio_value),
    cards_count: toNullableFiniteNumber(summary.cards_count),
    sealed_count: toNullableFiniteNumber(summary.sealed_count),
    graded_count: toNullableFiniteNumber(summary.graded_count),
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

  const requestUrl = await buildPublicCollectionSummaryUrl(normalizedUsername);

  try {
    const response = await fetch(requestUrl, {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      cache: "no-store",
    });

    if (!response.ok) {
      return {
        data: null,
        warning: `Collection summary request failed for ${normalizedUsername}: ${response.status} ${response.statusText}`.trim(),
      };
    }

    const payload = await response.json();
    const summary = extractCollectionSummary(payload);

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
  }
}