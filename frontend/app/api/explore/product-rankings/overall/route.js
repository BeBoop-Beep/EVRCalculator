import { NextResponse } from "next/server";
import { getOverallProductRankings } from "@/lib/explore/overallProductRankingsServer";

export async function GET(request) {
  const budget = new URL(request.url).searchParams.get("budget") || "full_market";
  const result = await getOverallProductRankings(budget);
  return NextResponse.json(result, { status: result.status === "available" ? 200 : 503 });
}
