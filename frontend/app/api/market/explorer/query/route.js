import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

function forwardedAuthHeaders(request) {
  const headers = { Accept: "application/json" };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.Authorization = authorization;
  if (cookie) headers.Cookie = cookie;
  return headers;
}

async function proxy(request, path, init = {}) {
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}${path}`, {
    ...init,
    headers: { ...forwardedAuthHeaders(request), ...(init.headers || {}) },
    cache: "no-store",
  });
    return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json",
      "Cache-Control": "private, no-store",
    },
    });
  } catch (error) {
    if (process.env.NODE_ENV !== "production") console.error("Market Explorer query proxy failure", { errorCode: "MARKET_EXPLORER_QUERY_PROXY_UNAVAILABLE", errorName: error?.name || "Error" });
    return NextResponse.json({ message: "Market Explorer query service is temporarily unavailable", code: "MARKET_EXPLORER_QUERY_PROXY_UNAVAILABLE" }, { status: 503, headers: { "Cache-Control": "private, no-store" } });
  }
}

export async function GET(request) {
  return proxy(request, "/market/explorer/query/options");
}

export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { message: "A JSON query specification is required", code: "MARKET_EXPLORER_QUERY_INVALID" },
      { status: 400 }
    );
  }
  return proxy(request, "/market/explorer/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
