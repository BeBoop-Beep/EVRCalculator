import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const HEADERS = { "Cache-Control": "public, max-age=60, stale-while-revalidate=300" };
export async function GET(request) {
  try {
    const response = await fetch(`${getBackendApiBaseUrl()}/tcgs/pokemon/rankings/product-catalogue${request.nextUrl.search}`, { cache: "no-store", signal: request.signal });
    return NextResponse.json(await response.json(), { status: response.status, headers: HEADERS });
  } catch {
    return NextResponse.json({ message: "Product catalogue is temporarily unavailable." }, { status: 503, headers: HEADERS });
  }
}
