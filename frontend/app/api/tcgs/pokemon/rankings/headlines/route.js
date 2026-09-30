import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const HEADERS = { "Cache-Control": "public, max-age=60, stale-while-revalidate=300" };
export async function GET(request) {
  const entityType = new URL(request.url).searchParams.get("entity_type");
  if (!new Set(["set", "era"]).has(entityType)) return NextResponse.json({ message: "entity_type must be set or era" }, { status: 400 });
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}/tcgs/pokemon/rankings/headlines?entity_type=${entityType}`, { cache: "no-store", signal: request.signal });
    return NextResponse.json(await response.json(), { status: response.status, headers: HEADERS });
  } catch {
    return NextResponse.json({ message: "Public Rankings headlines are temporarily unavailable." }, { status: 503, headers: HEADERS });
  }
}
