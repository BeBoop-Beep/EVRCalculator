import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { EXPLORER_PROXY_BOUNDS_MS, fetchExplorerRead } from "@/lib/explore/marketExplorerReadProxy.mjs";

function forwardedAuthHeaders(request) {
  const headers = { Accept: "application/json" };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.Authorization = authorization;
  if (cookie) headers.Cookie = cookie;
  return headers;
}

async function proxy(request, path, init = {}) {
  try {
    const result = await fetchExplorerRead({ url: `${getBackendApiBaseUrl()}${path}`,
      init: { ...init, headers: { ...forwardedAuthHeaders(request), ...(init.headers || {}) } },
      requestSignal: request.signal, timeoutMs: EXPLORER_PROXY_BOUNDS_MS.constituents,
      operation: "query_constituents" });
    console.info("market_explorer_proxy_read", { operation: "query_constituents", elapsedMs: result.elapsedMs, attempts: result.attempts, status: result.response.status });
    return new NextResponse(result.text, { status: result.response.status, headers: {
      "content-type": result.response.headers.get("content-type") || "application/json", "Cache-Control": "private, no-store" } });
  } catch (error) {
    const timedOut = error?.proxyTimedOut === true;
    return NextResponse.json({ message: timedOut ? "Constituents took too long to load. Please try again." : "Constituents are temporarily unavailable.", code: timedOut ? "QUERY_CONSTITUENTS_TIMEOUT" : "QUERY_CONSTITUENTS_UNAVAILABLE" }, { status: timedOut ? 504 : 503, headers: { "Cache-Control": "private, no-store" } });
  }
}

// A thin, unopinionated proxy — identical shape to the sibling `query` route —
// to the backend's paginated constituent-page RPC wrapper. This route carries
// NO paging logic of its own: `limit`/`afterRank` pass straight through, and
// the backend re-derives the query fingerprint from the posted spec rather
// than trusting one from the client.
export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { message: "A JSON query specification is required", code: "MARKET_EXPLORER_QUERY_INVALID" },
      { status: 400 }
    );
  }
  return proxy(request, "/market/explorer/query/constituents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
