// Active route handler for public profile collection summary. Consumed via publicCollectionSummaryAccessor.js.
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

function summarizeCollectionPayload(payload) {
  const items = Array.isArray(payload?.collection_items) ? payload.collection_items : [];
  const byType = items.reduce((acc, item) => {
    const key = String(item?.collectible_type || "unknown");
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  return {
    count: items.length,
    byType,
  };
}

export async function GET(req, { params }) {
  const { username: usernameParam } = await params;
  const rawUsername = typeof usernameParam === "string" ? usernameParam.trim() : "";

  if (!rawUsername) {
    return NextResponse.json({ error: "Invalid username." }, { status: 400 });
  }

  const backendUrl = new URL(`${getBackendBaseUrl()}/collection/items/public/${encodeURIComponent(rawUsername)}`);
  req.nextUrl.searchParams.forEach((value, key) => {
    backendUrl.searchParams.append(key, value);
  });

  const correlationId = req.headers.get("x-correlation-id") || crypto.randomUUID();
  const proxyHeaders = await buildProxyHeaders(req);
  proxyHeaders["x-correlation-id"] = correlationId;

  console.info("[public-collection-proxy] request_start", {
    correlationId,
    username: rawUsername,
    backendUrl: backendUrl.toString(),
    includeCollectionItems: req.nextUrl.searchParams.get("include_collection_items"),
  });

  const proxyResponse = await fetch(backendUrl.toString(), {
    method: "GET",
    headers: proxyHeaders,
    credentials: "include",
    cache: "no-store",
  });

  const payload = await proxyResponse.text();
  const contentType = proxyResponse.headers.get("content-type") || "application/json";
  const backendCorrelationId = proxyResponse.headers.get("x-correlation-id") || correlationId;

  let payloadSummary = { count: null, byType: {} };
  try {
    payloadSummary = summarizeCollectionPayload(JSON.parse(payload));
  } catch {
    payloadSummary = { count: null, byType: {} };
  }

  console.info("[public-collection-proxy] response", {
    correlationId: backendCorrelationId,
    username: rawUsername,
    status: proxyResponse.status,
    ok: proxyResponse.ok,
    count: payloadSummary.count,
    byType: payloadSummary.byType,
    payloadSizeBytes: Buffer.byteLength(payload, "utf8"),
  });

  return new NextResponse(payload, {
    status: proxyResponse.status,
    headers: {
      "content-type": contentType,
      "x-correlation-id": backendCorrelationId,
    },
  });
}