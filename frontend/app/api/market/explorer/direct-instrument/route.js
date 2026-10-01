import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
import { EXPLORER_REQUEST_BOUNDS_MS } from "@/lib/explore/marketExplorerBoundedRequest.mjs";

export async function POST(request) {
  let body;
  try { body = await request.text(); JSON.parse(body); }
  catch { return NextResponse.json({ message: "A valid direct-item request is required", code: "DIRECT_INSTRUMENT_PROXY_INVALID" }, { status: 400 }); }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), EXPLORER_REQUEST_BOUNDS_MS.directInstrument);
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}/market/explorer/direct-instrument`, {
      method: "POST", cache: "no-store", signal: controller.signal,
      headers: { Accept: "application/json", "Content-Type": "application/json" }, body,
    });
    return new NextResponse(await response.text(), { status: response.status,
      headers: { "content-type": response.headers.get("content-type") || "application/json", "Cache-Control": "public, max-age=0, must-revalidate" } });
  } catch (error) {
    const timedOut = error?.name === "AbortError";
    return NextResponse.json({ message: timedOut ? "Direct item history timed out" : "Direct item history is temporarily unavailable",
      code: timedOut ? "DIRECT_INSTRUMENT_TIMEOUT" : "DIRECT_INSTRUMENT_PROXY_UNAVAILABLE" }, { status: timedOut ? 504 : 503 });
  } finally { clearTimeout(timer); }
}
