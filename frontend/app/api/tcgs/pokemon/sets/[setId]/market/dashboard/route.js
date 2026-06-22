import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const PUBLIC_ANALYTICS_CACHE_CONTROL = "public, s-maxage=300, stale-while-revalidate=3600";
const FAILED_ANALYTICS_CACHE_CONTROL = "no-store";

function shouldBypassCache(request) {
  if (process.env.NODE_ENV === "production") {
    return false;
  }
  const params = request?.nextUrl?.searchParams;
  return params?.get("cache") === "no-store" || params?.get("bypassCache") === "1";
}

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
    `${getBackendApiBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/market/dashboard`
  );
  const window = request?.nextUrl?.searchParams?.get("window");
  if (window) {
    backendUrl.searchParams.set("window", window);
  }
  const days = request?.nextUrl?.searchParams?.get("days");
  if (days) {
    backendUrl.searchParams.set("days", days);
  }

  const bypassCache = shouldBypassCache(request);
  const proxyResponse = await fetch(backendUrl.toString(), {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });

  const payload = await proxyResponse.text();
  const contentType = proxyResponse.headers.get("content-type") || "application/json";
  const cacheControl =
    bypassCache || !proxyResponse.ok ? FAILED_ANALYTICS_CACHE_CONTROL : PUBLIC_ANALYTICS_CACHE_CONTROL;

  return new NextResponse(payload, {
    status: proxyResponse.status,
    headers: {
      "content-type": contentType,
      "Cache-Control": cacheControl,
    },
  });
}
