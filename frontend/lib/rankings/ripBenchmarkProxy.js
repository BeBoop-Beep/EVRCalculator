import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const HEADERS = { "Cache-Control": "private, no-store", Vary: "Cookie, Authorization" };

export async function proxyRipBenchmark(request, endpoint) {
  let body;
  try { body = await request.json(); }
  catch { return NextResponse.json({ detail: { code: "INVALID_JSON", message: "A JSON body is required." } }, { status: 400, headers: HEADERS }); }
  // Browser callers select entities and dates only. Model authority is resolved
  // by the backend and these fields are rejected at this boundary as well.
  if (body?.benchmark_key !== undefined || body?.calibration_version !== undefined) {
    return NextResponse.json({ detail: { code: "MODEL_AUTHORITY_FORBIDDEN", message: "Benchmark authority is server-resolved." } }, { status: 400, headers: HEADERS });
  }
  const headers = { Accept: "application/json", "Content-Type": "application/json" };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.Authorization = authorization;
  if (cookie) headers.Cookie = cookie;
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}/tcgs/pokemon/rip-benchmark/${endpoint}`, {
      method: "POST", headers, body: JSON.stringify(body), cache: "no-store", signal: request.signal,
    });
    const text = await response.text();
    return new NextResponse(text, { status: response.status, headers: { ...HEADERS, "Content-Type": response.headers.get("content-type") || "application/json" } });
  } catch {
    return NextResponse.json({ detail: { code: "RIP_BENCHMARK_UPSTREAM_UNAVAILABLE", message: "Benchmark service is unavailable." } }, { status: 503, headers: HEADERS });
  }
}
