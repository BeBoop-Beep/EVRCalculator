import { NextResponse } from "next/server";
import { getOverallProductRankings } from "@/lib/explore/overallProductRankingsServer";

export async function GET(request) {
  const budget = new URL(request.url).searchParams.get("budget") || "full_market";
  const result = await getOverallProductRankings(budget, request);
  const payload = result?.data || {
    available: false,
    reason: result?.reason || "publication_unavailable",
    rows: [],
    availableBudgets: [],
  };
  return NextResponse.json(payload, {
    status: payload.available === true ? 200 : 503,
    headers: { "Cache-Control": "no-store", Vary: "Cookie, Authorization" },
  });
}
