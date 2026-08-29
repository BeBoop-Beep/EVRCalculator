import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const DETAIL_REVALIDATE_SECONDS = 120;

export async function GET(request, { params }) {
  const values = (await params) || {};
  const setId = String(values.setId || "").trim();
  const cardId = String(values.cardId || "").trim();
  if (!setId || !cardId) {
    return NextResponse.json(
      { message: "Set and card ids are required", code: "CARD_DETAIL_IDS_REQUIRED" },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }
  const url = new URL(`${getBackendApiBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/cards/${encodeURIComponent(cardId)}`);
  const variant = request.nextUrl.searchParams.get("variant_id");
  if (variant) url.searchParams.set("variant_id", variant);

  const response = await fetch(url.toString(), {
    headers: { Accept: "application/json" },
    next: {
      revalidate: DETAIL_REVALIDATE_SECONDS,
      tags: [`pokemon-card-detail:${setId}:${cardId}:${variant || "canonical"}`],
    },
  });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json",
      // Browser navigations still revalidate through the application route;
      // the expensive backend read is what is deduplicated by Next's data cache.
      "Cache-Control": "private, max-age=0, must-revalidate",
    },
  });
}
