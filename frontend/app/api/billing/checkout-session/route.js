import { NextResponse } from "next/server";
import { proxyBilling } from "@/lib/billing/billingProxy";
export const dynamic = "force-dynamic";
export async function POST(request) {
  let body;
  try { body = await request.json(); } catch { return NextResponse.json({ detail: { code: "INVALID_REQUEST" } }, { status: 400 }); }
  return proxyBilling(request, "/billing/checkout-session", { method: "POST", body });
}
