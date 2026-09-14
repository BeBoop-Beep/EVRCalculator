import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export async function POST(request) {
  let body;
  try { body = await request.json(); }
  catch { return NextResponse.json({ message: "A JSON query specification is required", code: "QUERY_INVALID" }, { status: 400 }); }
  const headers = { Accept: "application/json", "Content-Type": "application/json" };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.Authorization = authorization;
  if (cookie) headers.Cookie = cookie;
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}/market/explorer/query/preflight`, {
      method: "POST", headers, body: JSON.stringify(body), cache: "no-store", signal: request.signal,
    });
    const responseHeaders = { "content-type": response.headers.get("content-type") || "application/json", "Cache-Control": "private, no-store" };
    const retryAfter = response.headers.get("Retry-After");
    if (retryAfter) responseHeaders["Retry-After"] = retryAfter;
    return new NextResponse(await response.text(), { status: response.status, headers: responseHeaders });
  } catch (error) {
    if (process.env.NODE_ENV !== "production") console.error("Market Explorer preflight proxy failure", { errorCode: "QUERY_PREFLIGHT_PROXY_UNAVAILABLE", errorName: error?.name || "Error" });
    return NextResponse.json({ message: "Market Explorer preflight service is temporarily unavailable", code: "QUERY_PREFLIGHT_PROXY_UNAVAILABLE" }, { status: 503, headers: { "Cache-Control": "private, no-store" } });
  }
}
