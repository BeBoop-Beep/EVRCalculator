import { benchmarkMetric } from "./ripBenchmarkPresentation.mjs";
export const productId = (row) => row?.sealedProductId || row?.sealed_product_id || row?.id || null;
export function compactFamilyBenchmarkLabel(value) {
  const label = String(value || "format").trim();
  if (/^elite trainer box$/i.test(label)) return "ETB";
  if (/^pokémon center elite trainer box$/i.test(label)) return "Pokémon Center ETB";
  if (/^loose booster pack$/i.test(label)) return "Loose Pack";
  if (/^sleeved booster pack$/i.test(label)) return "Sleeved Pack";
  return label || "format";
}
export function productBenchmarkMetrics(row, benchmark) {
  const id = productId(row); const context = { openingEconomicsReference: benchmark?.opening_economics_reference || null };
  return { overall: benchmarkMetric(benchmark?.rows, "sealed_product", id, "overall", context), financial: benchmarkMetric(benchmark?.rows, "sealed_product", id, "financial", context), chase: benchmarkMetric(benchmark?.rows, "sealed_product", id, "chase", context), collector: benchmarkMetric(benchmark?.rows, "sealed_product", id, "collector", context) };
}
export function withProductBenchmark(rows, benchmark) { return (rows || []).map((row) => ({ ...row, benchmarkMetrics: productBenchmarkMetrics(row, benchmark) })); }
export function setBenchmarkMetrics(setId, benchmark) { return { overall: benchmarkMetric(benchmark?.rows, "set", setId, "overall"), financial: benchmarkMetric(benchmark?.rows, "set", setId, "financial"), chase: benchmarkMetric(benchmark?.rows, "set", setId, "chase"), collector: benchmarkMetric(benchmark?.rows, "set", setId, "collector") }; }
