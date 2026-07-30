import { proxySlimSetModuleRequest } from "@/lib/pokemon/slimSetModuleProxyRoute";

// Forwarded params (window, limit, movement, snapshot_contract) and the
// bounded-timeout / cache-control policy live in
// lib/pokemon/slimSetModuleProxyContract.mjs. movement is part of the shared
// canonical Cards query contract the backend reads.
export async function GET(request, context) {
  return proxySlimSetModuleRequest("movers", request, context);
}
