// /app/api/auth/me/route.js
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
  try {
    const backendUrl = `${getBackendBaseUrl()}/auth/me`;
    const hasCookieHeader = Boolean(req.headers.get("cookie"));
    const hasAuthorizationHeader = Boolean(req.headers.get("authorization"));
    console.info("[auth/me proxy] inbound", {
      hasCookieHeader,
      hasAuthorizationHeader,
      backendUrl,
    });

    const proxyResponse = await fetch(backendUrl, {
      method: "GET",
      headers: buildProxyHeaders(req),
      credentials: "include",
      cache: "no-store",
    });

    console.info("[auth/me proxy] outbound", {
      status: proxyResponse.status,
      ok: proxyResponse.ok,
    });

    const payload = await proxyResponse.text();
    const contentType = proxyResponse.headers.get("content-type") || "application/json";

    return new NextResponse(payload, {
      status: proxyResponse.status,
      headers: {
        "content-type": contentType,
      },
    });
  } catch (error) {
    console.error("[auth/me proxy] failed", {
      message: error instanceof Error ? error.message : String(error),
    });
    if (error instanceof TypeError && String(error.message || "").toLowerCase().includes("fetch failed")) {
      return NextResponse.json(
        {
          message: "Backend auth service is unavailable. Ensure the Python backend is running and BACKEND_API_BASE_URL is correct.",
          backend_url: getBackendBaseUrl(),
        },
        { status: 503 }
      );
    }

    return NextResponse.json({ message: "Server error" }, { status: 500 });
  }
}
