import { NextResponse } from "next/server";

const PROFILE_ME_PATH = "/profile/me";

function getBackendBaseUrl() {
  return (process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

function buildProxyHeaders(request, includeJsonContentType = false) {
  const headers = {
    Accept: "application/json",
  };

  if (includeJsonContentType) {
    headers["Content-Type"] = "application/json";
  }

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
    const hasCookieHeader = Boolean(req.headers.get("cookie"));
    const hasAuthorizationHeader = Boolean(req.headers.get("authorization"));
    console.info("[profile proxy] inbound GET", {
      hasCookieHeader,
      hasAuthorizationHeader,
    });

    const proxyResponse = await fetch(`${getBackendBaseUrl()}${PROFILE_ME_PATH}`, {
      method: "GET",
      headers: buildProxyHeaders(req),
      credentials: "include",
      cache: "no-store",
    });

    console.info("[profile proxy] outbound GET", {
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
    if (error instanceof TypeError && String(error.message || "").toLowerCase().includes("fetch failed")) {
      return NextResponse.json(
        {
          message: "Backend profile service is unavailable. Ensure the Python backend is running and BACKEND_API_BASE_URL is correct.",
          backend_url: getBackendBaseUrl(),
        },
        { status: 503 }
      );
    }

    return NextResponse.json({ message: "Server error" }, { status: 500 });
  }
}

export async function PUT(req) {
  try {
    const hasCookieHeader = Boolean(req.headers.get("cookie"));
    const hasAuthorizationHeader = Boolean(req.headers.get("authorization"));
    console.info("[profile proxy] inbound PUT", {
      hasCookieHeader,
      hasAuthorizationHeader,
    });

    const payload = await req.json();
    const proxyResponse = await fetch(`${getBackendBaseUrl()}${PROFILE_ME_PATH}`, {
      method: "PUT",
      headers: buildProxyHeaders(req, true),
      body: JSON.stringify(payload),
      credentials: "include",
      cache: "no-store",
    });

    console.info("[profile proxy] outbound PUT", {
      status: proxyResponse.status,
      ok: proxyResponse.ok,
    });

    const responseBody = await proxyResponse.text();
    const contentType = proxyResponse.headers.get("content-type") || "application/json";

    return new NextResponse(responseBody, {
      status: proxyResponse.status,
      headers: {
        "content-type": contentType,
      },
    });
  } catch (error) {
    if (error instanceof SyntaxError) {
      return NextResponse.json({ message: "Invalid JSON body" }, { status: 400 });
    }

    if (error instanceof TypeError && String(error.message || "").toLowerCase().includes("fetch failed")) {
      return NextResponse.json(
        {
          message: "Backend profile service is unavailable. Ensure the Python backend is running and BACKEND_API_BASE_URL is correct.",
          backend_url: getBackendBaseUrl(),
        },
        { status: 503 }
      );
    }

    return NextResponse.json({ message: "Server error" }, { status: 500 });
  }
}
