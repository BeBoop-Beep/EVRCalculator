import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export async function GET(request, { params }) {
  const values = (await params) || {};
  const setId = String(values.setId || "").trim();
  const cardId = String(values.cardId || "").trim();
  if (!setId || !cardId) return NextResponse.json({ message: "Set and card ids are required", code: "CARD_CHASE_EFFICIENCY_IDS_REQUIRED" }, { status: 400 });
  const target = new URL(`${getBackendApiBaseUrl()}/tcgs/pokemon/sets/${encodeURIComponent(setId)}/cards/${encodeURIComponent(cardId)}/chase-efficiency`);
  const variantId = request.nextUrl.searchParams.get("variant_id");
  if (variantId) target.searchParams.set("variant_id", variantId);
  const headers = { Accept: "application/json" };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.Authorization = authorization;
  if (cookie) headers.Cookie = cookie;
  const response = await fetch(target, { headers, cache: "no-store" });
  return new NextResponse(await response.text(), { status: response.status,
    headers: { "content-type": response.headers.get("content-type") || "application/json", "Cache-Control": "private, no-store" } });
}
