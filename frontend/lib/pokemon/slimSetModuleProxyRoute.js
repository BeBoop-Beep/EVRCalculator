import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import {
  BACKEND_FETCH_TIMEOUT_MS,
  FAILED_ANALYTICS_CACHE_CONTROL,
  PUBLIC_ANALYTICS_CACHE_CONTROL,
  buildSlimSetModuleBackendUrl,
  buildSlimSetModuleProxyErrorBody,
  isAbortError,
  resolveSlimSetModuleCacheControl,
  slimSetModuleProxyErrorStatus,
} from "./slimSetModuleProxyContract.mjs";

export {
  BACKEND_FETCH_TIMEOUT_MS,
  FAILED_ANALYTICS_CACHE_CONTROL,
  PUBLIC_ANALYTICS_CACHE_CONTROL,
  resolveSlimSetModuleCacheControl,
};

function backendPathForDiagnostics(url) {
  return `${url.pathname}${url.search || ""}`;
}

/**
 * Shared GET proxy for the slim Pokemon set module routes.
 *
 * Behaviour that every one of the four routes now gets identically:
 *  - forwards exactly the params declared in SLIM_SET_MODULE_PROXY_CONTRACTS,
 *    unchanged;
 *  - bounds a stalled backend read with AbortController +
 *    BACKEND_FETCH_TIMEOUT_MS and answers with a structured, retryable 504
 *    (502 for a non-timeout transport failure) instead of hanging forever;
 *  - marks every failed response no-store so a failure is never cached, and
 *    applies the module's own success policy (see
 *    resolveSlimSetModuleCacheControl — /overview is no-store so a cached
 *    previous-market-date Opening Profit vs Cost payload can never be replayed
 *    after the row has been rebuilt);
 *  - passes a normal backend response through untouched — original status,
 *    original body, original content-type — so a slow-but-successful read is
 *    still a success and a backend 4xx/5xx keeps its own body.
 */
export async function proxySlimSetModuleRequest(moduleKey, request, context) {
  const resolvedParams = (await context?.params) || {};
  const setId = String(resolvedParams?.setId || "").trim();

  if (!setId) {
    return NextResponse.json({ message: "setId is required", code: "SET_ID_REQUIRED" }, { status: 400 });
  }

  const backendUrl = buildSlimSetModuleBackendUrl({
    baseUrl: getBackendApiBaseUrl(),
    moduleKey,
    setId,
    searchParams: request?.nextUrl?.searchParams,
  });

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), BACKEND_FETCH_TIMEOUT_MS);
  let proxyResponse;
  try {
    const authorization = request?.headers?.get("authorization");
    const cookie = request?.headers?.get("cookie");
    proxyResponse = await fetch(backendUrl.toString(), {
      method: "GET",
      headers: {
        Accept: "application/json",
        ...(authorization ? { Authorization: authorization } : {}),
        ...(cookie ? { Cookie: cookie } : {}),
      },
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    const timedOut = isAbortError(error);
    return NextResponse.json(
      buildSlimSetModuleProxyErrorBody({
        moduleKey,
        setId,
        timedOut,
        backendPath: backendPathForDiagnostics(backendUrl),
      }),
      {
        status: slimSetModuleProxyErrorStatus(timedOut),
        headers: { "Cache-Control": resolveSlimSetModuleCacheControl(moduleKey, { ok: false }) },
      }
    );
  } finally {
    clearTimeout(timeout);
  }

  const payload = await proxyResponse.text();
  const contentType = proxyResponse.headers.get("content-type") || "application/json";
  const cacheControl = resolveSlimSetModuleCacheControl(moduleKey, { ok: proxyResponse.ok });

  return new NextResponse(payload, {
    status: proxyResponse.status,
    headers: {
      "content-type": contentType,
      "Cache-Control": cacheControl,
      Vary: "Cookie, Authorization",
    },
  });
}
