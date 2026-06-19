import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

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
    `${getBackendApiBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/market/top-cards`
  );
  const limit = request?.nextUrl?.searchParams?.get("limit");
  if (limit) {
    backendUrl.searchParams.set("limit", limit);
  }
  const days = request?.nextUrl?.searchParams?.get("days");
  if (days) {
    backendUrl.searchParams.set("days", days);
  }

  const proxyResponse = await fetch(backendUrl.toString(), {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    cache: "no-store",
  });

  const payload = await proxyResponse.text();
  const contentType = proxyResponse.headers.get("content-type") || "application/json";

  return new NextResponse(payload, {
    status: proxyResponse.status,
    headers: {
      "content-type": contentType,
    },
  });
}
