import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

// Full set /page payloads can exceed Next's 2MB data-cache limit, so this
// route always bypasses Next's fetch cache and never emits a cacheable
// response — unlike the smaller module routes (cards, market, value-history),
// which stay on the public/CDN cache path.
const FAILED_ANALYTICS_CACHE_CONTROL = "no-store";
const BACKEND_FETCH_TIMEOUT_MS = 9000;

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
    `${getBackendApiBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/page`
  );

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), BACKEND_FETCH_TIMEOUT_MS);
  let proxyResponse;
  try {
    proxyResponse = await fetch(backendUrl.toString(), {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    const timedOut = isAbortError(error);
    const status = timedOut ? 504 : 502;
    const code = timedOut ? "SET_PAGE_SNAPSHOT_PROXY_TIMEOUT" : "SET_PAGE_SNAPSHOT_PROXY_ERROR";
    return NextResponse.json(
      {
        message: timedOut ? "Set page snapshot request timed out" : "Unable to load set page snapshot",
        code,
        retryable: true,
        setId,
        backendPath: backendPathForDiagnostics(backendUrl),
      },
      {
        status,
        headers: { "Cache-Control": FAILED_ANALYTICS_CACHE_CONTROL },
      }
    );
  } finally {
    clearTimeout(timeout);
  }

  const payload = await proxyResponse.text();
  const contentType = proxyResponse.headers.get("content-type") || "application/json";

  return new NextResponse(payload, {
    status: proxyResponse.status,
    headers: {
      "content-type": contentType,
      "Cache-Control": FAILED_ANALYTICS_CACHE_CONTROL,
    },
  });
}
