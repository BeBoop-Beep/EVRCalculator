import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const PUBLIC_ANALYTICS_CACHE_CONTROL = "public, s-maxage=300, stale-while-revalidate=3600";

export async function GET(request, { params }) {
  const resolvedParams = (await params) || {};
  const setId = String(resolvedParams?.setId || "").trim();
  const url = new URL(request.url);
  const isRetry = url.searchParams.get("retry") === "1";

  if (!setId) {
    return NextResponse.json(
      { message: "setId is required", code: "SET_ID_REQUIRED" },
      { status: 400 }
    );
  }

  const backendUrl = new URL(
    `${getBackendApiBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/page`
  );

  const proxyResponse = await fetch(backendUrl.toString(), {
    method: "GET",
    headers: { Accept: "application/json" },
    ...(isRetry ? { cache: "no-store" } : { next: { revalidate: 300 } }),
  });

  const payload = await proxyResponse.text();
  const contentType = proxyResponse.headers.get("content-type") || "application/json";

  return new NextResponse(payload, {
    status: proxyResponse.status,
    headers: {
      "content-type": contentType,
      "Cache-Control": isRetry ? "no-store" : PUBLIC_ANALYTICS_CACHE_CONTROL,
    },
  });
}
