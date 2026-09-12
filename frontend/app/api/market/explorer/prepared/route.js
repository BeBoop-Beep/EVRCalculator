import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

function headers(request) {
  const result = { Accept: "application/json" };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) result.Authorization = authorization;
  if (cookie) result.Cookie = cookie;
  return result;
}

async function forward(request, path, init = {}) {
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}${path}`, {
      ...init, headers: { ...headers(request), ...(init.headers || {}) }, cache: "no-store",
    });
    return new NextResponse(await response.text(), { status: response.status,
      headers: { "content-type": response.headers.get("content-type") || "application/json", "Cache-Control": "private, no-store" } });
  } catch (error) {
    if (process.env.NODE_ENV !== "production") console.error("Market Explorer prepared proxy failure", { errorCode: "PREPARED_PROXY_UNAVAILABLE", errorName: error?.name || "Error" });
    return NextResponse.json({ message: "Prepared Market Explorer data is temporarily unavailable", code: "PREPARED_PROXY_UNAVAILABLE" }, { status: 503, headers: { "Cache-Control": "private, no-store" } });
  }
}

export async function POST(request) {
  return forward(request, "/market/explorer/prepared-comparison", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(await request.json()),
  });
}

export async function GET(request) {
  const query = new URLSearchParams(request.nextUrl.searchParams);
  const kind = query.get("kind");
  query.delete("kind");
  if (kind === "screen") return forward(request, `/market/explorer/prepared-screen?${query.toString()}`);
  if (kind === "ranking") return forward(request, `/market/explorer/set-context-ranking?${query.toString()}`);
  return NextResponse.json({ message: "Unsupported prepared read" }, { status: 400 });
}
