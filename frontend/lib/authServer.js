import { cache } from "react";
import { cookies, headers } from "next/headers";

const API_URL = process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000";

const getRequestMeta = cache(async function getRequestMeta() {
  let correlationId = "";
  let incomingHeaderCorrelationId = null;

  try {
    const requestHeaders = await headers();
    incomingHeaderCorrelationId = requestHeaders.get("x-correlation-id");
    correlationId = String(incomingHeaderCorrelationId || "").trim() || crypto.randomUUID();
  } catch {
    correlationId = crypto.randomUUID();
  }

  return {
    correlationId,
    incomingHeaderCorrelationId,
  };
});

const resolveAuthenticatedUserFromCookiesPerRequest = cache(async function resolveAuthenticatedUserFromCookiesPerRequest() {
  const startedAt = Date.now();
  const { correlationId } = await getRequestMeta();
  const cookieStore = await cookies();
  const token = cookieStore.get("token")?.value;

  if (!token) {
    return {
      user: null,
      error: "Not authenticated",
      status: 401,
      correlationId,
      authResolution: "fresh",
      servedCount: 0,
      elapsedMs: Date.now() - startedAt,
    };
  }

  try {
    const response = await fetch(`${API_URL}/auth/me`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "x-correlation-id": correlationId,
      },
      cache: "no-store",
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data?.user) {
      return {
        user: null,
        error: data?.message || "Invalid or expired token",
        status: response.status || 401,
        correlationId,
        authResolution: "fresh",
        servedCount: 0,
        elapsedMs: Date.now() - startedAt,
      };
    }

    return {
      user: data.user,
      error: null,
      status: 200,
      correlationId,
      authResolution: "fresh",
      servedCount: 0,
      elapsedMs: Date.now() - startedAt,
    };
  } catch {
    return {
      user: null,
      error: "Auth service unavailable",
      status: 500,
      correlationId,
      authResolution: "fresh",
      servedCount: 0,
      elapsedMs: Date.now() - startedAt,
    };
  }
});

export async function getAuthenticatedUserFromCookies() {
  const startedAt = Date.now();
  const resolved = await resolveAuthenticatedUserFromCookiesPerRequest();
  resolved.servedCount += 1;

  const authResolution = resolved.servedCount > 1 ? "reused" : "fresh";
  const result = {
    user: resolved.user,
    error: resolved.error,
    status: resolved.status,
    correlationId: resolved.correlationId,
    authResolution,
  };

  console.info("[authServer] auth_resolution", {
    correlationId: resolved.correlationId,
    route: "authServer.getAuthenticatedUserFromCookies",
    authResolution,
    status: resolved.status,
    userId: resolved.user?.id || null,
    elapsedMs: Date.now() - startedAt,
    freshResolveElapsedMs: resolved.elapsedMs,
  });

  return result;
}
