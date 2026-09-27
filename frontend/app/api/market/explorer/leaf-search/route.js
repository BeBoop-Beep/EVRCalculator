import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export const dynamic = "force-dynamic";
const ASSETS = new Set(["cards", "sealed", "graded"]);
const NO_STORE = { "Cache-Control": "no-store" };

/** Public leaf-only Explorer search proxy. Execution remains separately gated. */
export async function GET(request) {
  const incoming = new URL(request.url);
  const q = (incoming.searchParams.get("q") || "").trim();
  const asset = (incoming.searchParams.get("asset") || "cards").toLowerCase();
  const limit = Number.parseInt(incoming.searchParams.get("limit") || "12", 10);
  if (!ASSETS.has(asset) || q.length < 2 || q.length > 120 || limit < 1 || limit > 50) {
    return NextResponse.json({ message: "Invalid leaf search request.", code: "LEAF_SEARCH_INVALID" }, { status: 400, headers: NO_STORE });
  }
  const url = new URL("/market/explorer/leaves/search", getBackendApiBaseUrl());
  url.search = new URLSearchParams({ asset, q, limit: String(limit) }).toString();
  try {
    const response = await fetch(url, { cache: "no-store", signal: request.signal });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const code = typeof payload?.code === "string" ? payload.code : "LEAF_SEARCH_FAILED";
      return NextResponse.json({ message: "Leaf search is temporarily unavailable.", code }, { status: response.status === 400 ? 400 : response.status === 429 ? 429 : 503, headers: NO_STORE });
    }
    return NextResponse.json({ query: payload?.query || q, asset, limit,
      items: Array.isArray(payload?.items) ? payload.items : [],
      availability: payload?.availability, reason: payload?.reason }, { status: 200, headers: NO_STORE });
  } catch {
    return NextResponse.json({ message: "Leaf search is temporarily unavailable.", code: "LEAF_SEARCH_PROXY_UNAVAILABLE" }, { status: 503, headers: NO_STORE });
  }
}
