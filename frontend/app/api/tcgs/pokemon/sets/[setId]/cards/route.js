import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const PUBLIC_ANALYTICS_CACHE_CONTROL = "public, s-maxage=900, stale-while-revalidate=86400";

function getBackendBaseUrl() {
  return getBackendApiBaseUrl();
}

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
    `${getBackendBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/cards`
  );

  const bypassCache = shouldBypassCache(request);
  const proxyResponse = await fetch(backendUrl.toString(), {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    ...(bypassCache ? { cache: "no-store" } : { next: { revalidate: 900 } }),
  });

  const payload = await proxyResponse.text();
  const contentType = proxyResponse.headers.get("content-type") || "application/json";

  return new NextResponse(payload, {
    status: proxyResponse.status,
    headers: {
      "content-type": contentType,
      "Cache-Control": bypassCache ? "no-store" : PUBLIC_ANALYTICS_CACHE_CONTROL,
    },
  });
}
