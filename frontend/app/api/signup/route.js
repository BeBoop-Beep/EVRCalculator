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
    const proxyResponse = await fetch(`${getBackendBaseUrl()}/auth/signup`, {
      method: "POST",
      headers: buildProxyHeaders(req),
      body: JSON.stringify(body),
      credentials: "include",
      cache: "no-store",
    });

    const payload = await proxyResponse.json().catch(() => ({}));
    const responsePayload = { ...payload };
    const token = responsePayload?.token;
    if (token) {
      delete responsePayload.token;
    }

    const response = NextResponse.json(responsePayload, { status: proxyResponse.status });

    if (proxyResponse.ok && token) {
      response.cookies.set("token", token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      maxAge: 60 * 60 * 24,
      path: "/",
      sameSite: "lax",
    });
    }

    return response;
  } catch (error) {
    console.error("Error during signup:", error);
    return NextResponse.json({ error: "Server error. Please try again later." }, { status: 500 });
  }
}
