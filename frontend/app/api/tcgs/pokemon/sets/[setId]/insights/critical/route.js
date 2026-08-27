import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { getAuthenticatedUserFromCookies } from "@/lib/authServer";
import { applySetRipEntitlement } from "@/lib/pokemon/setRipEntitlement.mjs";

const PUBLIC_ANALYTICS_CACHE_CONTROL = "no-store";
const FAILED_ANALYTICS_CACHE_CONTROL = "no-store";

export async function GET(request, { params }) {
  const resolvedParams = (await params) || {};
  const setId = String(resolvedParams?.setId || "").trim();

  if (!setId) {
    return NextResponse.json(
      { message: "setId is required", code: "SET_ID_REQUIRED" },
      { status: 400 }
    );
  }

  const backendUrl = new URL(
    `${getBackendApiBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/insights/critical`
  );

  const proxyResponse = await fetch(backendUrl.toString(), {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
  });

  const payload = await proxyResponse.text();
  const contentType = proxyResponse.headers.get("content-type") || "application/json";
  const cacheControl = proxyResponse.ok ? PUBLIC_ANALYTICS_CACHE_CONTROL : FAILED_ANALYTICS_CACHE_CONTROL;

  if (proxyResponse.ok && contentType.includes("application/json")) {
    const auth = await getAuthenticatedUserFromCookies();
    return NextResponse.json(applySetRipEntitlement(JSON.parse(payload), auth?.user || null), {
      status: proxyResponse.status,
      headers: { "Cache-Control": "no-store", Vary: "Cookie, Authorization" },
    });
  }

  return new NextResponse(payload, {
    status: proxyResponse.status,
    headers: {
      "content-type": contentType,
      "Cache-Control": cacheControl,
    },
  });
}
