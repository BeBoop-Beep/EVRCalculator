import { proxySlimSetModuleRequest } from "@/lib/pokemon/slimSetModuleProxyRoute";

export async function GET(request, context) {
  return proxySlimSetModuleRequest("sealed-summary", request, context);
}
