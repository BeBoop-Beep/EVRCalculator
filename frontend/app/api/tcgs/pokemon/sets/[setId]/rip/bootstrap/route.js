import { proxySetRipProjection } from "@/lib/pokemon/setRipProjectionProxy";

export async function GET(request, { params }) {
  return proxySetRipProjection(request, (await params)?.setId, "bootstrap");
}
