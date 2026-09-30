import { proxyMarketActivity } from "@/lib/explore/marketActivityProxy";

export const dynamic = "force-dynamic";

export async function POST(request) {
  return proxyMarketActivity(request, "/market/explorer/activity");
}
