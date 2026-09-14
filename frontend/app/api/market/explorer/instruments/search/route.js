import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export const dynamic = "force-dynamic";

export async function GET(request) {
  const incoming = new URL(request.url);
  const q = incoming.searchParams.get("q") || "";
  const asset = incoming.searchParams.get("asset") || "all";
  const limit = incoming.searchParams.get("limit") || "20";
  if (q.trim().length < 2) return NextResponse.json({ message: "Enter at least 2 characters." }, { status: 400 });
  const url = new URL("/market/explorer/instruments/search", getBackendApiBaseUrl());
  url.searchParams.set("q", q.trim());
  url.searchParams.set("asset", asset);
  url.searchParams.set("limit", limit);
  const headers = {};
  const cookie = request.headers.get("cookie");
  const authorization = request.headers.get("authorization");
  if (cookie) headers.cookie = cookie;
  if (authorization) headers.authorization = authorization;
  try {
    const response = await fetch(url, { headers, cache: "no-store", signal: request.signal });
    const payload = await response.json().catch(() => ({ message: "Unable to search exact items." }));
    return NextResponse.json(payload, { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "Exact-item search is temporarily unavailable." }, { status: 502 });
  }
}
