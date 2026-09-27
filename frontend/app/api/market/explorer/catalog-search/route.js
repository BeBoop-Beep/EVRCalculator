import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export const dynamic = "force-dynamic";

const ASSETS = new Set(["cards", "sealed", "graded"]);
const NO_STORE = { "Cache-Control": "no-store" };

// Contextual Explorer catalog search proxy. General discovery (not plan-gated);
// forwards cookie + authorization, never caches, and never returns raw upstream
// error text to the browser.
export async function GET(request) {
  const incoming = new URL(request.url);
  const q = (incoming.searchParams.get("q") || "").trim();
  const asset = (incoming.searchParams.get("asset") || "cards").toLowerCase();
  const limit = Math.min(Math.max(Number.parseInt(incoming.searchParams.get("limit") || "20", 10) || 20, 1), 50);
  if (!ASSETS.has(asset)) return NextResponse.json({ message: "Unsupported search asset.", code: "CATALOG_SEARCH_INVALID" }, { status: 400, headers: NO_STORE });
  if (q.length < 2) return NextResponse.json({ message: "Enter at least 2 characters.", code: "CATALOG_SEARCH_INVALID" }, { status: 400, headers: NO_STORE });
  const url = new URL("/market/explorer/catalog/search", getBackendApiBaseUrl());
  url.searchParams.set("asset", asset);
  url.searchParams.set("q", q);
  url.searchParams.set("limit", String(limit));
  const headers = {};
  const cookie = request.headers.get("cookie");
  const authorization = request.headers.get("authorization");
  if (cookie) headers.cookie = cookie;
  if (authorization) headers.authorization = authorization;
  try {
    const response = await fetch(url, { headers, cache: "no-store", signal: request.signal });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const code = typeof payload?.code === "string" ? payload.code : "CATALOG_SEARCH_FAILED";
      return NextResponse.json({ message: "Search is temporarily unavailable.", code }, { status: response.status === 400 ? 400 : response.status === 429 ? 429 : 503, headers: NO_STORE });
    }
    return NextResponse.json({ results: Array.isArray(payload?.results) ? payload.results : [] }, { status: 200, headers: NO_STORE });
  } catch {
    return NextResponse.json({ message: "Search is temporarily unavailable.", code: "CATALOG_SEARCH_PROXY_UNAVAILABLE" }, { status: 503, headers: NO_STORE });
  }
}
