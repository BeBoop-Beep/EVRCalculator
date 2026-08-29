import { NextResponse } from "next/server";
import { isPublicAnalyticsEligiblePokemonSet } from "@/lib/pokemon/pokemonSetPublicCoverage";
import { projectRankingsTargets } from "@/lib/explore/rankingsClientProjection.mjs";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export const dynamic = "force-dynamic";

function marketDate(payload) {
  return payload?.meta?.comparisonSnapshots?.currentMarketDate || null;
}

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function rankTargets(targets) {
  return [...targets].sort((left, right) => {
    const leftRank = number(left?.setRipV1?.rank);
    const rightRank = number(right?.setRipV1?.rank);
    if (leftRank !== null && rightRank !== null && leftRank !== rightRank) return leftRank - rightRank;
    if (leftRank !== null && rightRank === null) return -1;
    if (leftRank === null && rightRank !== null) return 1;
    const leftScore = number(left?.setRipV1?.score) ?? -Infinity;
    const rightScore = number(right?.setRipV1?.score) ?? -Infinity;
    if (leftScore !== rightScore) return rightScore - leftScore;
    return String(left?.name || "").localeCompare(String(right?.name || ""));
  });
}

async function preparedLensPayloadForRequest(lens, request) {
  const url = new URL(`${getBackendApiBaseUrl()}/explore/rankings/lens/${encodeURIComponent(lens)}`);
  url.searchParams.set("limit", "60");
  const headers = { Accept: "application/json" };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.Authorization = authorization;
  if (cookie) headers.Cookie = cookie;
  const response = await fetch(url, { headers, cache: "no-store" });
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload) return null;
  return payload;
}

export async function GET(request) {
  const lens = String(request.nextUrl.searchParams.get("lens") || "").trim().toLowerCase();

  if (lens === "sets") {
    const payload = await preparedLensPayloadForRequest("sets", request);
    if (!payload || payload?.meta?.requestFailed) {
      return NextResponse.json(
        { status: "unavailable", targets: [], marketDate: marketDate(payload) },
        { status: 503, headers: { "Cache-Control": "private, no-store" } },
      );
    }
    const eligible = (Array.isArray(payload?.targets) ? payload.targets : [])
      .filter(isPublicAnalyticsEligiblePokemonSet);
    return NextResponse.json(
      {
        status: "available",
        targets: projectRankingsTargets(rankTargets(eligible), {
          canViewRankingsIntelligence: payload?.access?.rankingsIntelligence === true,
        }),
        access: payload?.access || { rankingsIntelligence: false, requiredPlan: "plus" },
        marketDate: marketDate(payload),
      },
      { headers: { "Cache-Control": "no-store", Vary: "Cookie, Authorization" } },
    );
  }

  if (lens === "eras") {
    const payload = await preparedLensPayloadForRequest("eras", request);
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
      { headers: { "Cache-Control": "no-store", Vary: "Cookie, Authorization" } },
    );
  }

  if (lens === "products") {
    const payload = await preparedLensPayloadForRequest("products", request);
    const overallProductRankings = payload?.overallProductRankings || {
      status: "unavailable", reason: "publication_unavailable", data: null,
    };
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
      { headers: { "Cache-Control": "no-store", Vary: "Cookie, Authorization" } },
    );
  }

  return NextResponse.json(
    { status: "bad_request", message: "Unsupported rankings lens" },
    { status: 400, headers: { "Cache-Control": "no-store" } },
  );
}
