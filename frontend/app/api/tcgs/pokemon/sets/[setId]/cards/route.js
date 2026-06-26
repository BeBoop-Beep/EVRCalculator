import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const PUBLIC_ANALYTICS_CACHE_CONTROL = "public, s-maxage=900, stale-while-revalidate=86400";
const FAILED_ANALYTICS_CACHE_CONTROL = "no-store";
const BACKEND_FETCH_TIMEOUT_MS = 15000;

function getBackendBaseUrl() {
  return getBackendApiBaseUrl();
}

function shouldBypassCache(request) {
  if (process.env.NODE_ENV === "production") {
    return false;
  }
  const params = request?.nextUrl?.searchParams;
  return params?.get("cache") === "no-store" || params?.get("bypassCache") === "1";
}

function backendPathForDiagnostics(url) {
  return `${url.pathname}${url.search || ""}`;
}

function isAbortError(error) {
  return error?.name === "AbortError" || String(error?.message || "").toLowerCase().includes("abort");
}

export async function GET(request, { params }) {
  const resolvedParams = (await params) || {};
  const setId = String(resolvedParams?.setId || "").trim();

  if (!setId) {
    return NextResponse.json(
      { message: "setId is required", code: "SET_ID_REQUIRED" },
      { status: 400 }
    );
  }

  const backendUrl = new URL(
    `${getBackendBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/cards`
  );

  const bypassCache = shouldBypassCache(request);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), BACKEND_FETCH_TIMEOUT_MS);
  let proxyResponse;
  try {
    proxyResponse = await fetch(backendUrl.toString(), {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    const timedOut = isAbortError(error);
    const status = timedOut ? 504 : 502;
    const code = timedOut ? "POKEMON_SET_CARDS_TIMEOUT" : "POKEMON_SET_CARDS_PROXY_ERROR";
    return NextResponse.json(
      {
        message: timedOut ? "Timed out loading Pokemon set cards" : "Unable to load Pokemon set cards",
        code,
        retryable: true,
        setId,
        backendPath: backendPathForDiagnostics(backendUrl),
      },
      {
        status,
        headers: {
          "Cache-Control": FAILED_ANALYTICS_CACHE_CONTROL,
        },
      }
    );
  } finally {
    clearTimeout(timeout);
  }

  const payload = await proxyResponse.text();
  const contentType = proxyResponse.headers.get("content-type") || "application/json";
  const cacheControl =
    bypassCache || !proxyResponse.ok ? FAILED_ANALYTICS_CACHE_CONTROL : PUBLIC_ANALYTICS_CACHE_CONTROL;

  return new NextResponse(payload, {
    status: proxyResponse.status,
    headers: {
      "content-type": contentType,
      "Cache-Control": cacheControl,
    },
  });
}
