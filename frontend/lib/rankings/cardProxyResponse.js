import { NextResponse } from "next/server";

export const CARD_PROXY_HEADERS = {
  "Cache-Control": "private, no-store",
  Vary: "Cookie, Authorization",
};

export async function cardProxyResponse(fetchUpstream) {
  try {
    const response = await fetchUpstream();
    const text = await response.text();
    let payload;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { message: "Card Rankings backend returned an invalid response." };
    }
    return NextResponse.json(payload, { status: response.status, headers: CARD_PROXY_HEADERS });
  } catch {
    return NextResponse.json(
      { message: "Card Rankings backend is temporarily unavailable." },
      { status: 503, headers: CARD_PROXY_HEADERS },
    );
  }
}
