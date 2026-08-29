import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export async function GET(request, { params }) {
  const { productId } = await params;
  const id = String(productId || "").trim();
  if (!id) {
    return NextResponse.json(
      { message: "Sealed product id is required", code: "SEALED_PRODUCT_ID_REQUIRED" },
      { status: 400, headers: { "Cache-Control": "no-store" } },
    );
  }

  const headers = { Accept: "application/json" };
  const authorization = request.headers.get("authorization");
  const cookie = request.headers.get("cookie");
  if (authorization) headers.Authorization = authorization;
  if (cookie) headers.Cookie = cookie;
  const response = await fetch(`${getBackendApiBaseUrl()}/tcgs/pokemon/sealed-products/${encodeURIComponent(id)}`, {
    headers,
    cache: "no-store",
  });
  const payload = await response.json().catch(() => ({ message: "Invalid backend response" }));
  return NextResponse.json(payload, {
    status: response.status,
    headers: { "Cache-Control": "no-store", Vary: "Cookie, Authorization" },
  });
}
