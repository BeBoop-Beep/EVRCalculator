import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { EXPLORER_PROXY_BOUNDS_MS, fetchExplorerRead } from "@/lib/explore/marketExplorerReadProxy.mjs";

export const dynamic = "force-dynamic";

const ASSETS = new Set(["cards", "sealed", "graded"]);
const NO_STORE = { "Cache-Control": "no-store" };

// Truthful rarity / sealed-type availability states published by the database,
// through the backend. No raw upstream error text reaches the browser.
export async function GET(request) {
  const asset = (new URL(request.url).searchParams.get("asset") || "cards").toLowerCase();
  if (!ASSETS.has(asset)) return NextResponse.json({ message: "Unsupported asset.", code: "ASSET_OPTIONS_INVALID" }, { status: 400, headers: NO_STORE });
  const url = new URL("/market/explorer/asset-options", getBackendApiBaseUrl());
  url.searchParams.set("asset", asset);
  const headers = {};
  const cookie = request.headers.get("cookie");
  const authorization = request.headers.get("authorization");
  if (cookie) headers.cookie = cookie;
  if (authorization) headers.authorization = authorization;
  try {
    const result = await fetchExplorerRead({ url, init: { headers }, requestSignal: request.signal,
      timeoutMs: EXPLORER_PROXY_BOUNDS_MS.assetOptions, operation: "asset_options" });
    const { response, payload } = result;
    console.info("market_explorer_proxy_read", { operation: "asset_options", elapsedMs: result.elapsedMs, attempts: result.attempts, status: response.status });
    if (!response.ok || !payload || typeof payload !== "object") {
      const code = typeof payload?.code === "string" ? payload.code : "ASSET_OPTIONS_FAILED";
      return NextResponse.json({ message: "Options are temporarily unavailable.", code }, { status: response.status === 400 ? 400 : 503, headers: NO_STORE });
    }
    return NextResponse.json(payload, { status: 200, headers: NO_STORE });
  } catch (error) {
    const timedOut = error?.proxyTimedOut === true;
    return NextResponse.json({ message: timedOut ? "Options took too long to load." : "Options are temporarily unavailable.", code: timedOut ? "ASSET_OPTIONS_PROXY_TIMEOUT" : "ASSET_OPTIONS_PROXY_UNAVAILABLE" }, { status: timedOut ? 504 : 503, headers: NO_STORE });
  }
}
