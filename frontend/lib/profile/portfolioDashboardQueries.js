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

  return requestHeaders;
}

async function fetchBackendJson(path, options = {}) {
  const { searchParams = null, overrideUserId = null } = options;
  const url = buildBackendUrl(path, searchParams);

  const response = await fetch(url.toString(), {
    method: "GET",
    headers: await buildBackendHeaders(overrideUserId),
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
    return {
      data: null,
      error: {
        message: payload?.detail || payload?.message || `Request failed (${response.status})`,
        status: response.status,
      },
    };
  }

  return {
    data: payload,
    error: null,
  };
}

export async function getCurrentUserCollectionItems() {
  const result = await fetchBackendJson("/collection/items");

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
  const result = await fetchBackendJson("/collection/dashboard");

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
