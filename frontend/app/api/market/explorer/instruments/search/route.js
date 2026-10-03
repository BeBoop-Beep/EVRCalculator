import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { EXPLORER_PROXY_BOUNDS_MS, fetchExplorerRead } from "@/lib/explore/marketExplorerReadProxy.mjs";

export const dynamic = "force-dynamic";

export async function GET(request) {
  const incoming = new URL(request.url);
  const q = incoming.searchParams.get("q") || "";
  const asset = incoming.searchParams.get("asset") || "all";
  const limit = incoming.searchParams.get("limit") || "20";
  if (q.trim().length < 2) return NextResponse.json({ message: "Enter at least 2 characters." }, { status: 400 });
  const url = new URL("/market/explorer/instruments/search", getBackendApiBaseUrl());
  url.searchParams.set("q", q.trim());
  url.searchParams.set("asset", asset);
  url.searchParams.set("limit", limit);
  const headers = {};
  const cookie = request.headers.get("cookie");
  const authorization = request.headers.get("authorization");
  if (cookie) headers.cookie = cookie;
  if (authorization) headers.authorization = authorization;
  try {
    const result = await fetchExplorerRead({ url, init: { headers }, requestSignal: request.signal,
      timeoutMs: EXPLORER_PROXY_BOUNDS_MS.exactSearch, operation: "exact_item_search" });
    const { response, payload } = result;
    console.info("market_explorer_proxy_read", { operation: "exact_item_search", elapsedMs: result.elapsedMs, attempts: result.attempts, status: response.status });
    return NextResponse.json(payload || { message: "Unable to search exact items." }, { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const timedOut = error?.proxyTimedOut === true;
    return NextResponse.json({ message: timedOut ? "Exact-item search took too long. Please try again." : "Exact-item search is temporarily unavailable.", code: timedOut ? "EXACT_SEARCH_PROXY_TIMEOUT" : "EXACT_SEARCH_PROXY_UNAVAILABLE" }, { status: timedOut ? 504 : 503, headers: { "Cache-Control": "no-store" } });
  }
}
