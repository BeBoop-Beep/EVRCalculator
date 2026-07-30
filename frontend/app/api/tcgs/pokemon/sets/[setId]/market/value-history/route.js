import { proxySlimSetModuleRequest } from "@/lib/pokemon/slimSetModuleProxyRoute";

// Forwarded params (days, scope->value_scope, snapshot_contract) and the
// bounded-timeout / cache-control policy live in
// lib/pokemon/slimSetModuleProxyContract.mjs.
export async function GET(request, context) {
  return proxySlimSetModuleRequest("value-history", request, context);
}
