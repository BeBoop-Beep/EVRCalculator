import { proxySlimSetModuleRequest } from "@/lib/pokemon/slimSetModuleProxyRoute";

// Forwarded params (window, limit, snapshot_contract) and the bounded-timeout /
// cache-control policy live in lib/pokemon/slimSetModuleProxyContract.mjs.
export async function GET(request, context) {
  return proxySlimSetModuleRequest("top-chase", request, context);
}
