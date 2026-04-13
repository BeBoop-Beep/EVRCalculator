import { NextResponse } from "next/server";

function getBackendBaseUrl() {
  return (process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

function buildProxyHeaders(request) {
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

export async function POST(req) {
  try {
    const body = await req.json();
    // Keep legacy frontend route available, but use canonical backend login path.
    const proxyResponse = await fetch(`${getBackendBaseUrl()}/auth/login`, {
      method: "POST",
      headers: buildProxyHeaders(req),
      body: JSON.stringify(body),
      credentials: "include",
      cache: "no-store",
    });

    const payload = await proxyResponse.json().catch(() => ({}));
    const response = NextResponse.json(payload, { status: proxyResponse.status });

    if (proxyResponse.ok && payload?.token) {
      response.cookies.set("token", payload.token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === "production",
        sameSite: "lax",
        maxAge: 60 * 60 * 24,
        path: "/",
      });
    }

    return response;
  } catch (error) {
    console.error("Error during login:", error);

    if (error instanceof TypeError && String(error.message || "").toLowerCase().includes("fetch failed")) {
      return NextResponse.json(
        {
          message: "Backend auth service is unavailable. Ensure the Python backend is running and BACKEND_API_BASE_URL is correct.",
          backend_url: getBackendBaseUrl(),
        },
        { status: 503 }
      );
    }

    return NextResponse.json(
      { message: "Server error. Please try again later." },
      { status: 500 }
    );
  }
}
