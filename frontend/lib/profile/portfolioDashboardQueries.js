import { headers } from "next/headers";
import { getAuthenticatedUserFromCookies } from "@/lib/authServer";

function getBackendBaseUrl() {
  return (process.env.BACKEND_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
}

function buildBackendUrl(path, searchParams = null) {
  const baseUrl = getBackendBaseUrl();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${baseUrl}${normalizedPath}`);

  if (searchParams) {
    searchParams.forEach((value, key) => {
      url.searchParams.append(key, value);
    });
  }

  return url;
}

async function buildBackendHeaders(overrideUserId = null) {
  const requestHeaders = {
    Accept: "application/json",
    "x-correlation-id": crypto.randomUUID(),
  };

  try {
    const incomingHeaders = await headers();
    const cookieHeader = incomingHeaders.get("cookie");
    const authorizationHeader = incomingHeaders.get("authorization");

    if (cookieHeader) {
      requestHeaders.cookie = cookieHeader;
    }

    if (authorizationHeader) {
      requestHeaders.authorization = authorizationHeader;
    }
  } catch {
    // Ignore header extraction failures for non-request contexts.
  }

  if (overrideUserId) {
    requestHeaders["x-user-id"] = String(overrideUserId);
    return requestHeaders;
  }

  const authResult = await getAuthenticatedUserFromCookies();
  if (authResult?.user?.id) {
    requestHeaders["x-user-id"] = String(authResult.user.id);
  }

  console.info("[portfolioDashboardQueries] auth_resolution", {
    correlationId: requestHeaders["x-correlation-id"],
    route: "portfolioDashboardQueries.buildBackendHeaders",
    authResolution: authResult?.authResolution || "unknown",
    userId: authResult?.user?.id || null,
  });

  return requestHeaders;
}

async function fetchBackendJson(path, options = {}) {
  const { searchParams = null, overrideUserId = null, traceLabel = "backend_fetch" } = options;
  const startedAt = Date.now();
  const url = buildBackendUrl(path, searchParams);
  const headers = await buildBackendHeaders(overrideUserId);
  const correlationId = headers["x-correlation-id"];

  console.info("[portfolioDashboardQueries] request_start", {
    correlationId,
    route: traceLabel,
    path,
  });

  const response = await fetch(url.toString(), {
    method: "GET",
    headers,
    credentials: "include",
    cache: "no-store",
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    console.info("[portfolioDashboardQueries] request_end", {
      correlationId,
      route: traceLabel,
      path,
      status: response.status,
      ok: false,
      payloadSizeBytes: payload ? JSON.stringify(payload).length : 0,
      elapsedMs: Date.now() - startedAt,
    });
    return {
      data: null,
      error: {
        message: payload?.detail || payload?.message || `Request failed (${response.status})`,
        status: response.status,
      },
    };
  }

  console.info("[portfolioDashboardQueries] request_end", {
    correlationId,
    route: traceLabel,
    path,
    status: response.status,
    ok: true,
    payloadSizeBytes: payload ? JSON.stringify(payload).length : 0,
    elapsedMs: Date.now() - startedAt,
  });

  return {
    data: payload,
    error: null,
  };
}

export async function getCurrentUserCollectionItems() {
  const searchParams = new URLSearchParams();
  searchParams.set("limit", "200");
  searchParams.set("offset", "0");
  searchParams.set("include_private_fields", "0");
  const result = await fetchBackendJson("/collection/items", {
    searchParams,
    traceLabel: "collection_items_bounded",
  });

  if (result.error) {
    return {
      data: null,
      error: result.error,
    };
  }

  return {
    data: Array.isArray(result.data?.collection_items) ? result.data.collection_items : [],
    error: null,
  };
}

export async function getCurrentUserPortfolioDashboardData() {
  const result = await fetchBackendJson("/collection/dashboard", {
    traceLabel: "dashboard_snapshot",
  });

  if (result.error) {
    return {
      data: null,
      error: result.error,
    };
  }

  return {
    data: result.data?.dashboard || result.data,
    error: null,
  };
}

export async function getCurrentUserCollectionEntryById(entryId) {
  const result = await fetchBackendJson(`/collection/entries/${encodeURIComponent(String(entryId || "").trim())}`, {
    traceLabel: "collection_entry_detail_owner",
  });

  if (result.error) {
    return {
      data: null,
      error: result.error,
    };
  }

  return {
    data: result.data?.entry || null,
    error: null,
  };
}

export async function getPublicCollectionEntryByUsernameAndItemId(username, itemId) {
  const normalizedUsername = String(username || "").trim();
  const normalizedItemId = String(itemId || "").trim();
  const result = await fetchBackendJson(`/collection/items/public/${encodeURIComponent(normalizedUsername)}/entry/${encodeURIComponent(normalizedItemId)}`, {
    traceLabel: "collection_entry_detail_public",
  });

  if (result.error) {
    return {
      data: null,
      error: result.error,
    };
  }

  return {
    data: result.data?.entry || null,
    error: null,
  };
}
