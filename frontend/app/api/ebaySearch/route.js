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

export async function GET(request) {
  const backendUrl = new URL(`${getBackendBaseUrl()}/integrations/ebay/search`);
  request.nextUrl.searchParams.forEach((value, key) => {
    backendUrl.searchParams.append(key, value);
  });

  const proxyResponse = await fetch(backendUrl.toString(), {
    method: "GET",
    headers: buildProxyHeaders(request),
    credentials: "include",
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