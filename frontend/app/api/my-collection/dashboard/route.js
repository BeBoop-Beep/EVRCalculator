import { NextResponse } from "next/server";
import { getAuthenticatedUserFromCookies } from "@/lib/authServer";

function getBackendBaseUrl() {
  return (process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

async function buildProxyHeaders(request) {
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

  const authResult = await getAuthenticatedUserFromCookies();
  if (authResult?.user?.id) {
    headers["x-user-id"] = String(authResult.user.id);
  }

  return headers;
}

export async function GET(request) {
  const backendUrl = new URL(`${getBackendBaseUrl()}/collection/dashboard`);
  request.nextUrl.searchParams.forEach((value, key) => {
    backendUrl.searchParams.append(key, value);
  });

  const proxyResponse = await fetch(backendUrl.toString(), {
    method: "GET",
    headers: await buildProxyHeaders(request),
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
