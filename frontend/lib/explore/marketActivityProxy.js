import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { EXPLORER_REQUEST_BOUNDS_MS } from "./marketExplorerBoundedRequest.mjs";

const RESPONSE_HEADERS = {
  "Cache-Control": "private, no-store",
  Vary: "Cookie, Authorization",
};

export async function proxyMarketActivity(request, backendPath) {
  let body;
  try {
    body = await request.text();
    if (!body) throw new Error("missing body");
    JSON.parse(body);
  } catch {
    return NextResponse.json(
      {
        message: "A JSON Market Activity request is required",
        code: "MARKET_ACTIVITY_PROXY_INVALID",
      },
      { status: 400, headers: RESPONSE_HEADERS },
    );
  }

  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
  };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.Authorization = authorization;
  if (cookie) headers.Cookie = cookie;

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), EXPLORER_REQUEST_BOUNDS_MS.activity);
    try {
    const response = await fetch(`${getBackendApiBaseUrl()}${backendPath}`, {
      method: "POST",
      headers,
      body,
      cache: "no-store",
      signal: controller.signal,
    });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: {
        ...RESPONSE_HEADERS,
        "content-type":
          response.headers.get("content-type") || "application/json",
      },
    });
    } finally { clearTimeout(timer); }
  } catch (error) {
    if (process.env.NODE_ENV !== "production") {
      console.error("Market Activity proxy failure", {
        errorCode: "MARKET_ACTIVITY_PROXY_UNAVAILABLE",
        errorName: error?.name || "Error",
      });
    }
    const timedOut = error?.name === "AbortError";
    return NextResponse.json(
      {
        message: timedOut ? "Market Activity read timed out" : "Market Activity is temporarily unavailable",
        code: timedOut ? "MARKET_ACTIVITY_TIMEOUT" : "MARKET_ACTIVITY_PROXY_UNAVAILABLE",
      },
      { status: timedOut ? 504 : 503, headers: RESPONSE_HEADERS },
    );
  }
}
