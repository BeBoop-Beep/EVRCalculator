import assert from "node:assert/strict";
import test from "node:test";
import { benchmarkPosition, formatBenchmarkFreshness, formatBenchmarkScore, normalizeBenchmarkMetric } from "./ripBenchmarkPresentation.mjs";
test("displayed 5.0 is the Pokémon benchmark baseline", () => { assert.equal(formatBenchmarkScore(5), "5.0 / 10"); assert.equal(benchmarkPosition(5.04), "At Pokémon benchmark"); });
test("display classification uses the same one-decimal score users see", () => { assert.equal(benchmarkPosition(5.05), "Above Pokémon benchmark"); assert.equal(benchmarkPosition(4.94), "Below Pokémon benchmark"); });
test("missing Benchmark score is unavailable and never zero", () => { assert.equal(formatBenchmarkScore(null), "Unavailable"); assert.equal(normalizeBenchmarkMetric({ benchmark_status: "unavailable", benchmark_score: 0 }).score, null); });
test("canonical rank remains independent of rounded score", () => { const metric = normalizeBenchmarkMetric({ benchmark_status: "available", benchmark_score: 10, rank: 2, cohort_size: 22 }); assert.equal(metric.rank, 2); assert.equal(metric.score, 10); });
test("freshness reads backend authority", () => { assert.equal(formatBenchmarkFreshness({ benchmarkMarketDate: "2026-09-25" }), "As of Sep 25"); });
