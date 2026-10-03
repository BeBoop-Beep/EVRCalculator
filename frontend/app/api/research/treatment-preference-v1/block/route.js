import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const HEADERS = {
  "Cache-Control": "private, no-store",
};

export async function GET(request) {
  const sessionId = new URL(request.url).searchParams.get("sessionId") || "";
  if (!sessionId) {
    return NextResponse.json(
      { message: "Anonymous study session is required.", code: "TREATMENT_PREFERENCE_SESSION_REQUIRED" },
      { status: 400, headers: HEADERS },
    );
  }

  try {
    const url = new URL(`${getBackendApiBaseUrl()}/research/treatment-preference-v1/block`);
    url.searchParams.set("sessionId", sessionId);
    const response = await fetch(url, {
      cache: "no-store",
      signal: request.signal,
      headers: { Accept: "application/json" },
    });
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: {
        ...HEADERS,
        "content-type": response.headers.get("content-type") || "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      {
        message: "The preference study is temporarily unavailable.",
        code: "TREATMENT_PREFERENCE_COLLECTION_UNAVAILABLE",
      },
      { status: 503, headers: HEADERS },
    );
  }
}
