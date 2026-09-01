import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

function authHeaders(request, json = false) {
  const headers = { Accept: "application/json" };
  if (json) headers["Content-Type"] = "application/json";
  const cookie = request.headers.get("cookie");
  const authorization = request.headers.get("authorization");
  if (cookie) headers.cookie = cookie;
  if (authorization) headers.authorization = authorization;
  return headers;
}

export async function proxyBilling(request, path, { method = "GET", body } = {}) {
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}${path}`, {
      method, headers: authHeaders(request, body !== undefined),
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "include", cache: "no-store",
    });
    const text = await response.text();
    return new NextResponse(text, { status: response.status, headers: {
      "content-type": response.headers.get("content-type") || "application/json",
      "Cache-Control": "no-store", "Vary": "Cookie, Authorization",
    }});
  } catch {
    return NextResponse.json({ detail: { code: "BILLING_SERVICE_UNAVAILABLE" } }, {
      status: 503, headers: { "Cache-Control": "no-store", "Vary": "Cookie, Authorization" },
    });
  }
}
