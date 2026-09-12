import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export const dynamic = "force-dynamic";

export async function GET(request) {
  const incoming = new URL(request.url);
  const q = (incoming.searchParams.get("q") || "").trim();
  const limit = incoming.searchParams.get("limit") || "20";
  if (q.length < 2) return NextResponse.json({ message: "Enter at least 2 characters." }, { status: 400 });
  const url = new URL("/search", getBackendApiBaseUrl());
  url.searchParams.set("q", q);
  url.searchParams.set("limit", limit);
  try {
    const response = await fetch(url, { cache: "no-store", signal: request.signal,
      headers: { "x-forwarded-for": request.headers.get("x-forwarded-for") || "" } });
    const payload = await response.json().catch(() => ({ message: "Search is temporarily unavailable." }));
    return NextResponse.json(payload, { status: response.status, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "Search is temporarily unavailable." }, { status: 502 });
  }
}
