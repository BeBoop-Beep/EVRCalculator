import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const FAILED_ANALYTICS_CACHE_CONTROL = "no-store";
const FORWARDED_PARAMS = ["max_cards", "include_plot_rows"];

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
    `${getBackendApiBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/cards/validation`
  );
  FORWARDED_PARAMS.forEach((param) => {
    const value = request?.nextUrl?.searchParams?.get(param);
    if (value) {
      backendUrl.searchParams.set(param, value);
    }
  });

  const proxyResponse = await fetch(backendUrl.toString(), {
    method: "GET",
    headers: {
      Accept: "application/json",
      ...(request.headers.get("authorization") ? { Authorization: request.headers.get("authorization") } : {}),
      ...(request.headers.get("cookie") ? { Cookie: request.headers.get("cookie") } : {}),
    },
    cache: "no-store",
  });

  const payload = await proxyResponse.text();
  const contentType = proxyResponse.headers.get("content-type") || "application/json";
  const cacheControl = FAILED_ANALYTICS_CACHE_CONTROL;

  return new NextResponse(payload, {
    status: proxyResponse.status,
    headers: {
      "content-type": contentType,
      "Cache-Control": cacheControl,
      Vary: "Cookie, Authorization",
    },
  });
}
