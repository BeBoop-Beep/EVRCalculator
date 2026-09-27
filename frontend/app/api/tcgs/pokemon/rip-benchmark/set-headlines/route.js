import { proxyRipBenchmark } from "@/lib/rankings/ripBenchmarkProxy";

export const dynamic = "force-dynamic";
export function POST(request) { return proxyRipBenchmark(request, "set-headlines"); }
