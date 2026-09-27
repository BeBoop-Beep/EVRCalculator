import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";
export const dynamic = "force-dynamic";
const RESPONSE_HEADERS = { "Cache-Control": "private, no-store", Vary: "Cookie, Authorization" };
const generation = (payload) => JSON.stringify([payload?.publication_id, payload?.market_date, payload?.calibration_version, payload?.cohort_fingerprint, payload?.freshness]);
export async function POST(request) {
  let body; try { body = await request.json(); } catch { return NextResponse.json({ detail: { code: "INVALID_JSON" } }, { status: 400, headers: RESPONSE_HEADERS }); }
  if (body?.benchmark_key !== undefined || body?.calibration_version !== undefined) return NextResponse.json({ detail: { code: "MODEL_AUTHORITY_FORBIDDEN" } }, { status: 400, headers: RESPONSE_HEADERS });
  const entities = [...new Map((Array.isArray(body?.entities) ? body.entities : []).map((entity) => [`${entity?.entity_type}:${entity?.entity_id}`, entity])).values()];
  if (!entities.length || entities.length > 200) return NextResponse.json({ detail: { code: "INVALID_ENTITY_COUNT" } }, { status: 422, headers: RESPONSE_HEADERS });
  const headers = { Accept: "application/json", "Content-Type": "application/json" }; const authorization = request.headers.get("authorization"); const cookie = request.headers.get("cookie"); if (authorization) headers.Authorization = authorization; if (cookie) headers.Cookie = cookie;
  try {
    const chunks = Array.from({ length: Math.ceil(entities.length / 10) }, (_, index) => entities.slice(index * 10, index * 10 + 10));
    const responses = await Promise.all(chunks.map((chunk) => fetch(`${getBackendApiBaseUrl()}/tcgs/pokemon/rip-benchmark/current`, { method: "POST", headers, cache: "no-store", body: JSON.stringify({ entities: chunk }), signal: request.signal })));
    const failed = responses.find((response) => !response.ok); if (failed) return new NextResponse(await failed.text(), { status: failed.status, headers: { ...RESPONSE_HEADERS, "Content-Type": failed.headers.get("content-type") || "application/json" } });
    const payloads = await Promise.all(responses.map((response) => response.json())); const expected = generation(payloads[0]);
    if (payloads.some((payload) => generation(payload) !== expected)) return NextResponse.json({ detail: { code: "MIXED_BENCHMARK_GENERATIONS", message: "Benchmark publication changed; refresh required." } }, { status: 409, headers: RESPONSE_HEADERS });
    return NextResponse.json({ ...payloads[0], backendRequestCount: chunks.length, rows: payloads.flatMap((payload) => payload.rows || []) }, { headers: RESPONSE_HEADERS });
  } catch { return NextResponse.json({ detail: { code: "RIP_BENCHMARK_UPSTREAM_UNAVAILABLE" } }, { status: 503, headers: RESPONSE_HEADERS }); }
}
