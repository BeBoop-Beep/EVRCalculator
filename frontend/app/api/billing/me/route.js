import { proxyBilling } from "@/lib/billing/billingProxy";
export const dynamic = "force-dynamic";
export function GET(request) { return proxyBilling(request, "/billing/me"); }
