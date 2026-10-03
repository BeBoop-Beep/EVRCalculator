import { NextResponse } from "next/server";
import { getBackendApiBaseUrl } from "@/lib/runtimeUrls";

const HEADERS = {
  "Cache-Control": "private, no-store",
};

export async function POST(request) {
  let body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { message: "Invalid request body.", code: "TREATMENT_PREFERENCE_BODY_INVALID" },
      { status: 400, headers: HEADERS },
    );
  }

  try {
    const response = await fetch(
      `${getBackendApiBaseUrl()}/research/treatment-preference-v1/submit`,
      {
        method: "POST",
        cache: "no-store",
        signal: request.signal,
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      },
    );
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
        message: "The preference responses could not be recorded.",
        code: "TREATMENT_PREFERENCE_SUBMISSION_UNAVAILABLE",
      },
      { status: 503, headers: HEADERS },
    );
  }
}
