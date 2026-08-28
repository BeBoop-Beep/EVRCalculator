import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { getAuthenticatedUserFromCookies } from "@/lib/authServer";
import { applySetRipEntitlement } from "@/lib/pokemon/setRipEntitlement.mjs";

const TIMEOUT_MS = 9000;
const PRIVATE_HEADERS = { "Cache-Control": "no-store", Vary: "Cookie, Authorization" };

export async function proxySetRipProjection(request, setId, suffix, { entitled = false } = {}) {
  const id = String(setId || "").trim();
  if (!id) return NextResponse.json({ message: "setId is required", code: "SET_ID_REQUIRED" }, { status: 400 });
  const backendUrl = new URL(`${getBackendApiBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(id)}/rip/${suffix}`);
  backendUrl.search = new URL(request.url).search;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(backendUrl, {
      cache: "no-store",
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(request.headers.get("authorization") ? { Authorization: request.headers.get("authorization") } : {}),
        ...(request.headers.get("cookie") ? { Cookie: request.headers.get("cookie") } : {}),
      },
    });
    const text = await response.text();
    if (!response.ok) return new NextResponse(text, { status: response.status, headers: { ...PRIVATE_HEADERS, "content-type": response.headers.get("content-type") || "application/json" } });
    const payload = JSON.parse(text);
    if (!entitled) return NextResponse.json(payload, { status: response.status, headers: { "Cache-Control": "no-store" } });
    const auth = await getAuthenticatedUserFromCookies();
    return NextResponse.json(applySetRipEntitlement(payload, auth?.user || null), { status: response.status, headers: PRIVATE_HEADERS });
  } catch (error) {
    const timedOut = error?.name === "AbortError";
    return NextResponse.json({ message: timedOut ? "Set RIP request timed out" : "Unable to load Set RIP data", code: timedOut ? "SET_RIP_PROXY_TIMEOUT" : "SET_RIP_PROXY_ERROR", retryable: true }, { status: timedOut ? 504 : 502, headers: PRIVATE_HEADERS });
  } finally {
    clearTimeout(timer);
  }
}
