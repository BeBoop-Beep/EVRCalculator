import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

function getBackendBaseUrl() {
  return getBackendApiBaseUrl();
}

async function buildProxyHeaders(request) {
  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
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

export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ message: "Invalid request body" }, { status: 400 });
  }

  const backendUrl = `${getBackendBaseUrl()}/tools/pack-simulator`;

  const proxyResponse = await fetch(backendUrl, {
    method: "POST",
    headers: await buildProxyHeaders(request),
    body: JSON.stringify(body),
    credentials: "include",
    cache: "no-store",
  });

  const payload = await proxyResponse.text();
  const contentType = proxyResponse.headers.get("content-type") || "application/json";

  return new NextResponse(payload, {
    status: proxyResponse.status,
    headers: { "content-type": contentType },
  });
}
