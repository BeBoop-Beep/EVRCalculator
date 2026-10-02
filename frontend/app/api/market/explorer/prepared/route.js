import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { EXPLORER_REQUEST_BOUNDS_MS } from "@/lib/explore/marketExplorerBoundedRequest.mjs";
import { EXPLORER_PROXY_BOUNDS_MS, fetchExplorerRead } from "@/lib/explore/marketExplorerReadProxy.mjs";

function headers(request) {
  const result = { Accept: "application/json" };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) result.Authorization = authorization;
  if (cookie) result.Cookie = cookie;
  return result;
}

async function forward(request, path, init = {}) {
  const timeoutMs = init.timeoutMs || EXPLORER_PROXY_BOUNDS_MS.prepared;
  const { timeoutMs: _timeoutMs, ...fetchInit } = init;
  try {
    const result = await fetchExplorerRead({
      url: `${getBackendApiBaseUrl()}${path}`, timeoutMs,
      operation: path, requestSignal: request.signal,
      init: {
      ...fetchInit,
      headers: { ...headers(request), ...(init.headers || {}) }, cache: "no-store",
      },
    });
    console.info("market_explorer_proxy_read", { operation: path, elapsedMs: result.elapsedMs, attempts: result.attempts, status: result.response.status });
    return new NextResponse(result.text, { status: result.response.status,
      headers: { "content-type": result.response.headers.get("content-type") || "application/json", "Cache-Control": "private, no-store" } });
  } catch (error) {
    if (process.env.NODE_ENV !== "production") console.error("Market Explorer prepared proxy failure", { errorCode: "PREPARED_PROXY_UNAVAILABLE", errorName: error?.name || "Error" });
    const timedOut = error?.proxyTimedOut === true;
    return NextResponse.json({ message: timedOut ? "Prepared Market Explorer read timed out" : "Prepared Market Explorer data is temporarily unavailable", code: timedOut ? "PREPARED_PROXY_TIMEOUT" : "PREPARED_PROXY_UNAVAILABLE" }, { status: timedOut ? 504 : 503, headers: { "Cache-Control": "private, no-store" } });
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
  if (kind === "screen") return forward(request, `/market/explorer/prepared-screen?${query.toString()}`, { timeoutMs: EXPLORER_REQUEST_BOUNDS_MS.screen });
  if (kind === "ranking") return forward(request, `/market/explorer/set-context-ranking?${query.toString()}`);
  if (kind === "constituents") return forward(request, `/market/explorer/prepared-constituents?${query.toString()}`, { timeoutMs: EXPLORER_PROXY_BOUNDS_MS.constituents });
  return NextResponse.json({ message: "Unsupported prepared read" }, { status: 400 });
}
