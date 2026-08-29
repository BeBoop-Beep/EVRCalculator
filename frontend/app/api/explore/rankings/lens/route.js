import { NextResponse } from "next/server";
import { getRipStatisticsTargets } from "@/lib/explore/ripStatisticsServer";
import { getOverallProductRankings } from "@/lib/explore/overallProductRankingsServer";

export const dynamic = "force-dynamic";

function marketDate(payload) {
  return payload?.meta?.comparisonSnapshots?.currentMarketDate || null;
}

export async function GET(request) {
  const lens = String(request.nextUrl.searchParams.get("lens") || "").trim().toLowerCase();

  if (lens === "eras") {
    const payload = await getRipStatisticsTargets({ limit: 60 }).catch(() => null);
    if (!payload || payload?.meta?.requestFailed) {
      return NextResponse.json(
        { status: "unavailable", eraSetStrength: null, marketDate: marketDate(payload) },
        { status: 503, headers: { "Cache-Control": "private, no-store" } },
      );
    }
    return NextResponse.json(
      {
        status: "available",
        eraSetStrength: payload?.eraSetStrengthV1 || null,
        marketDate: marketDate(payload),
      },
      { headers: { "Cache-Control": "private, max-age=0, must-revalidate" } },
    );
  }

  if (lens === "products") {
    const [payload, overallProductRankings] = await Promise.all([
      getRipStatisticsTargets({ limit: 60 }).catch(() => null),
      getOverallProductRankings("full_market"),
    ]);
    if (!payload || payload?.meta?.requestFailed) {
      return NextResponse.json(
        {
          status: "unavailable",
          productFamilyRankings: null,
          overallProductRankings,
          marketDate: marketDate(payload),
        },
        { status: 503, headers: { "Cache-Control": "private, no-store" } },
      );
    }
    return NextResponse.json(
      {
        status: "available",
        productFamilyRankings: payload?.productFamilyRankings || null,
        overallProductRankings,
        marketDate: marketDate(payload),
      },
      { headers: { "Cache-Control": "private, max-age=0, must-revalidate" } },
    );
  }

  return NextResponse.json(
    { status: "bad_request", message: "Unsupported rankings lens" },
    { status: 400, headers: { "Cache-Control": "no-store" } },
  );
}
