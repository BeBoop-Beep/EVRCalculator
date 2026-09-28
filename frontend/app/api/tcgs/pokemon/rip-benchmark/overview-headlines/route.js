import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export const dynamic = "force-dynamic";
const RESPONSE_HEADERS = {
  "Cache-Control": "public, s-maxage=300, stale-while-revalidate=3600",
};

export async function GET() {
  try {
    const response = await fetch(
      `${getBackendApiBaseUrl()}/tcgs/pokemon/rip-benchmark/overview-headlines`,
      { cache: "no-store", headers: { Accept: "application/json" } },
    );
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: {
        ...RESPONSE_HEADERS,
        "Content-Type": response.headers.get("content-type") || "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      {
        contractVersion: "rip-benchmark-overview-headlines-v1",
        status: "unavailable",
        marketDate: null,
        topSet: null,
        topEra: null,
      },
      { status: 503, headers: RESPONSE_HEADERS },
    );
  }
}
