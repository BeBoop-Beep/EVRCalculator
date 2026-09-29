import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export const dynamic = "force-dynamic";
const RESPONSE_HEADERS = { "Cache-Control": "private, no-store", Vary: "Cookie, Authorization" };

export async function GET(request) {
  const entityType = new URL(request.url).searchParams.get("entity_type");
  if (!["set", "era"].includes(entityType)) {
    return NextResponse.json({ message: "entity_type must be set or era" }, { status: 400, headers: RESPONSE_HEADERS });
  }
  const headers = { Accept: "application/json" };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.Authorization = authorization;
  if (cookie) headers.Cookie = cookie;
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}/tcgs/pokemon/rankings/scorecards?entity_type=${entityType}`, { headers, cache: "no-store", signal: request.signal });
    return new NextResponse(await response.text(), { status: response.status, headers: { ...RESPONSE_HEADERS, "Content-Type": response.headers.get("content-type") || "application/json" } });
  } catch {
    return NextResponse.json({ message: "Rankings scorecards are temporarily unavailable." }, { status: 503, headers: RESPONSE_HEADERS });
  }
}
