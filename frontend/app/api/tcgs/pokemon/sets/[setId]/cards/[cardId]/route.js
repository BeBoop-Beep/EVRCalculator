import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export async function GET(request, { params }) {
  const values = (await params) || {};
  const setId = String(values.setId || "").trim();
  const cardId = String(values.cardId || "").trim();
  if (!setId || !cardId) {
    return NextResponse.json({ message: "Set and card ids are required", code: "CARD_DETAIL_IDS_REQUIRED" }, { status: 400 });
  }
  const url = new URL(`${getBackendApiBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/cards/${encodeURIComponent(cardId)}`);
  const variant = request.nextUrl.searchParams.get("variant_id");
  if (variant) url.searchParams.set("variant_id", variant);
  const response = await fetch(url.toString(), { cache: "no-store", headers: { Accept: "application/json" } });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") || "application/json", "Cache-Control": "no-store" },
  });
}
