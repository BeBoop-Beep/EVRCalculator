import { proxySlimSetModuleRequest } from "@/lib/pokemon/slimSetModuleProxyRoute";

// Forwarded params (window, snapshot_contract) and the bounded-timeout /
// cache-control policy live in lib/pokemon/slimSetModuleProxyContract.mjs so
// this proxy cannot drift from getPokemonSetOverview's request again.
export async function GET(request, context) {
  return proxySlimSetModuleRequest("overview", request, context);
}
