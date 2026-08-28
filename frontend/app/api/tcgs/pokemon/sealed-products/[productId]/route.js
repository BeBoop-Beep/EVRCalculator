import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export const dynamic = "force-dynamic";

export async function GET(_request, { params }) {
  const { productId } = await params;
  const response = await fetch(`${getBackendApiBaseUrl()}/tcgs/pokemon/sealed-products/${encodeURIComponent(productId)}`, {
    cache: "no-store", headers: { Accept: "application/json" },
  });
  const payload = await response.json().catch(() => ({ message: "Invalid backend response" }));
  return NextResponse.json(payload, { status: response.status });
}
