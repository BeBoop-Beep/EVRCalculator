import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

export const dynamic = "force-dynamic";

export async function GET(request) {
  const incoming = new URL(request.url);
  const q = (incoming.searchParams.get("q") || "").trim();
  const limit = incoming.searchParams.get("limit") || "20";
  if (q.length < 2) return NextResponse.json({ message: "Enter at least 2 characters." }, { status: 400 });
  const proxyStarted = performance.now();
  let stage = "resolve-backend-url";
  try {
    const url = new URL("/search", getBackendApiBaseUrl());
    url.searchParams.set("q", q);
    url.searchParams.set("limit", limit);
    stage = "backend-fetch";
    const backendStarted = performance.now();
    const response = await fetch(url, { cache: "no-store", signal: request.signal,
      headers: { "x-forwarded-for": request.headers.get("x-forwarded-for") || "" } });
    const backendMs = performance.now() - backendStarted;
    stage = "decode-response";
    const payload = await response.json().catch(() => ({ message: "Search is temporarily unavailable." }));
    const proxyMs = performance.now() - proxyStarted;
    console.info("[api/search] complete", { status: response.status, backendMs: Math.round(backendMs), proxyMs: Math.round(proxyMs) });
    return NextResponse.json(payload, { status: response.status, headers: {
      "Cache-Control": "no-store", "Server-Timing": `backend;dur=${backendMs.toFixed(2)}, proxy;dur=${proxyMs.toFixed(2)}`,
    } });
  } catch (error) {
    console.error("[api/search] failed", { stage, error: error instanceof Error ? error.name : "UnknownError" });
    return NextResponse.json({ message: "Search is temporarily unavailable." }, { status: 502 });
  }
}
