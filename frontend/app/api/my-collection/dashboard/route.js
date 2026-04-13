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
  console.info("[my-collection-dashboard proxy] auth_resolution", {
    route: "/api/my-collection/dashboard",
    authResolution: authResult?.authResolution || "unknown",
    correlationId: authResult?.correlationId || null,
    userId: authResult?.user?.id || null,
  });
  if (authResult?.user?.id) {
    headers["x-user-id"] = String(authResult.user.id);
  }

  return headers;
}

export async function GET(request) {
  const routeStartedAt = Date.now();
  const correlationId = request.headers.get("x-correlation-id") || crypto.randomUUID();
  const includeCollectionItems = request.nextUrl.searchParams.get("include_collection_items") === "1";
  const backendUrl = new URL(`${getBackendBaseUrl()}/collection/dashboard`);
  request.nextUrl.searchParams.forEach((value, key) => {
    backendUrl.searchParams.append(key, value);
  });

  const headersWithAuth = await buildProxyHeaders(request);
  headersWithAuth["x-correlation-id"] = correlationId;

  console.info("[my-collection-dashboard proxy] request_start", {
    correlationId,
    route: "/api/my-collection/dashboard",
    backendPath: "/collection/dashboard",
    includeCollectionItems,
    authResolution: headersWithAuth["x-user-id"] ? "resolved" : "missing",
  });

  const backendStartedAt = Date.now();
  const proxyResponse = await fetch(backendUrl.toString(), {
    method: "GET",
    headers: headersWithAuth,
    credentials: "include",
    cache: "no-store",
  });

  const payload = await proxyResponse.text();
  const contentType = proxyResponse.headers.get("content-type") || "application/json";
  const payloadSizeBytes = Buffer.byteLength(payload, "utf8");
  let collectionItemCount = null;
  let pathUsed = "snapshot_only";

  try {
    const parsed = JSON.parse(payload);
    const items = Array.isArray(parsed?.collection_items) ? parsed.collection_items : [];
    collectionItemCount = items.length;
    pathUsed = includeCollectionItems ? "full_assembly" : "snapshot_only";
  } catch {
    collectionItemCount = null;
  }

  console.info("[my-collection-dashboard proxy] request_end", {
    correlationId,
    route: "/api/my-collection/dashboard",
    backendPath: "/collection/dashboard",
    includeCollectionItems,
    pathUsed,
    status: proxyResponse.status,
    payloadSizeBytes,
    collectionItemCount,
    backendElapsedMs: Date.now() - backendStartedAt,
    totalElapsedMs: Date.now() - routeStartedAt,
  });

  return new NextResponse(payload, {
    status: proxyResponse.status,
    headers: {
      "content-type": contentType,
      "x-correlation-id": proxyResponse.headers.get("x-correlation-id") || correlationId,
    },
  });
}
