import { NextResponse } from "next/server";

function getBackendBaseUrl() {
  return (process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

function buildProxyHeaders(request) {
  const headers = {
    Accept: "application/json",
  };

  const cookieHeader = request.headers.get("cookie");
  if (cookieHeader) {
    headers.cookie = cookieHeader;
  }

  const authorization = request.headers.get("authorization");
  if (authorization) {
    headers.authorization = authorization;
  }

  return headers;
}

export async function GET(req) {
  const proxyResponse = await fetch(`${getBackendBaseUrl()}/products`, {
    method: "GET",
    headers: buildProxyHeaders(req),
    cache: "no-store",
  });

  const payload = await proxyResponse.json().catch(() => ({}));
  if (!proxyResponse.ok) {
    return NextResponse.json(payload, { status: proxyResponse.status });
  }

  return NextResponse.json(Array.isArray(payload?.products) ? payload.products : [], { status: 200 });
}