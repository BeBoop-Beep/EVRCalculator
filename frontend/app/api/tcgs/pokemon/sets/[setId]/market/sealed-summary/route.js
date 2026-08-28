import { proxySlimSetModuleRequest } from "@/lib/pokemon/slimSetModuleProxy";

export async function GET(request, context) {
  return proxySlimSetModuleRequest("sealed-summary", request, context);
}
