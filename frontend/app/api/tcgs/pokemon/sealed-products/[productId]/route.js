import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const DETAIL_REVALIDATE_SECONDS = 120;

export async function GET(_request, { params }) {
  const { productId } = await params;
  const id = String(productId || "").trim();
  if (!id) {
    return NextResponse.json(
      { message: "Sealed product id is required", code: "SEALED_PRODUCT_ID_REQUIRED" },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }

  const response = await fetch(`${getBackendApiBaseUrl()}/tcgs/pokemon/sealed-products/${encodeURIComponent(id)}`, {
    headers: { Accept: "application/json" },
    next: {
      revalidate: DETAIL_REVALIDATE_SECONDS,
      tags: [`pokemon-sealed-product-detail:${id}`],
    },
  });
  const payload = await response.json().catch(() => ({ message: "Invalid backend response" }));
  return NextResponse.json(payload, {
    status: response.status,
    headers: { "Cache-Control": "private, max-age=0, must-revalidate" },
  });
}
