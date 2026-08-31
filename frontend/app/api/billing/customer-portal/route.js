import { proxyBilling } from "@/lib/billing/billingProxy";
export const dynamic = "force-dynamic";
export function POST(request) { return proxyBilling(request, "/billing/customer-portal", { method: "POST" }); }
