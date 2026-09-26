import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

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
    const response = await fetch(url, { headers, cache: "no-store", signal: request.signal });
    const payload = await response.json().catch(() => null);
    if (!response.ok || !payload || typeof payload !== "object") {
      const code = typeof payload?.code === "string" ? payload.code : "ASSET_OPTIONS_FAILED";
      return NextResponse.json({ message: "Options are temporarily unavailable.", code }, { status: response.status === 400 ? 400 : 503, headers: NO_STORE });
    }
    return NextResponse.json(payload, { status: 200, headers: NO_STORE });
  } catch {
    return NextResponse.json({ message: "Options are temporarily unavailable.", code: "ASSET_OPTIONS_PROXY_UNAVAILABLE" }, { status: 503, headers: NO_STORE });
  }
}
