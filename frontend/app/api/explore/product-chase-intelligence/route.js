import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

// Thin proxy to the PREMIUM-only backend Product Chase Intelligence
// endpoint. Mirrors app/api/explore/card-chase-efficiency/route.js exactly:
// entitlement is enforced server-side on the backend (see
// backend/api/main.py:_require_product_chase_intelligence), never here.
export async function GET(request) {
  const target = new URL(`${getBackendApiBaseUrl()}/explore/product-chase-intelligence`);
  for (const [key, value] of request.nextUrl.searchParams) target.searchParams.append(key, value);
  const headers = { Accept: "application/json" };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.Authorization = authorization;
  if (cookie) headers.Cookie = cookie;
  const response = await fetch(target, { headers, cache: "no-store" });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") || "application/json", "Cache-Control": "private, no-store", Vary: "Cookie, Authorization" },
  });
}
