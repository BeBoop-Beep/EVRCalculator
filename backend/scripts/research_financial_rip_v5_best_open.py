"""Read-only V5 Best-Open research adapter over the canonical exact-cent engine."""
from __future__ import annotations

import json
import math
import os
import time
import uuid
from array import array
from collections import Counter, defaultdict, OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import numpy as np
from scipy.stats import pearsonr, spearmanr

from backend.calculations.evr.best_open_price import (
    BEST_OPEN_PRICE_V2_METHOD_VERSION, PreparedCanonicalCandidate,
)
from backend.calculations.evr.best_open_price_v2_fused import DualBestOpenPriceSearch
from backend.calculations.evr.budget_normalized_product_ranking import build_budget_strategy_values
from backend.calculations.evr.financial_rip_v3 import PreparedFinancialRipDistribution
from backend.calculations.evr.financial_rip_v4 import project_financial_rip_v4_from_v3_payload
from backend.calculations.evr.financial_rip_v5_candidate import (
    CANDIDATE_ID, score_financial_rip_v5_candidate_with_control,
)
from backend.calculations.evr.sealed_product_distribution import (
    build_single_q_parity_distributions, single_q_parity_batch_width,
)
from backend.db.services.best_open_price_authority import validate_source
from backend.db.services.pack_outcome_artifact_service import load_pack_outcome_artifact
from backend.desirability.chase_accessibility_overall_score import chase_accessibility_overall_score
from backend.desirability.scoring_config import OVERALL_RIP_V12_WEIGHTS
from backend.desirability.weighted_rip import compute_overall_rip_v12
from backend.scripts.build_budget_normalized_product_rankings import build_stage1_distributions_cached, cohort_fingerprint
from backend.scripts.pokemon_snapshot_builders import get_client
from backend.scripts.run_best_open_price_v2_phase10b import _RssSampler
from backend.scripts.research_best_open_price_bucket0 import (
    _historical_authority, _load_exact_source_products, _load_source,
    _verify_v12_parity, validate_financial_only_rank_reconstructs,
    validate_rank_column_contiguous,
)

ROOT = Path(__file__).resolve().parents[2]
PROMPT2 = ROOT / "docs/research/financial_rip_v5_real_artifact_validation.json"
OUTPUT = ROOT / "docs/research/financial_rip_v5_best_open_live_validation.json"
CHECKPOINT = ROOT / "logs/financial_rip_v5_best_open_checkpoint.json"
CONTROL_OUTPUT = ROOT / "docs/research/financial_rip_v5_best_open_v2_control.json"
OVERALL_SHADOW_ID = "OVERALL_RIP_FINANCIAL_V5_SHADOW"
FINANCIAL_V5 = "financial_v5_candidate"
OVERALL_V5 = "overall_financial_v5_shadow"


def overall_shadow(financial_v5: float, chase_raw: float, collector: float) -> float:
    accessibility = chase_accessibility_overall_score(chase_raw)
    if accessibility is None or financial_v5 is None or collector is None:
        raise ValueError("Overall V5 shadow requires all three pillars")
    w = OVERALL_RIP_V12_WEIGHTS
    return round(w["financial_rip"] * financial_v5 + w["chase_accessibility"] * accessibility
                 + w["collector_appeal"] * collector, 4)


def financial_v5_key(row: Mapping[str, Any]) -> tuple:
    score = row["financialRipV5CandidateScore"]
    return (-float(score), str(row["sealedProductId"]))


def overall_v5_key(row: Mapping[str, Any]) -> tuple:
    return (-float(row["overallRipFinancialV5ShadowScore"]),
            -float(row["financialRipV5CandidateScore"]),
            -float(row["chanceToRecoverCapital"]),
            abs(float(row["actualCommittedCapital"]) - float(row["targetBudget"])),
            str(row["sealedProductId"]))


class PriceCollector:
    def __init__(self):
        self.seen: dict[str, set[tuple[int, int]]] = defaultdict(set)
        self.columns = {key: array("d") for key in (
            "pWin", "typical", "shortfall", "bee", "v4", "v5",
            "priceCents", "quantity", "p50Value", "loss", "trueWin",
            "overallV12", "overallV5", "committedCapital")}
        self.bucket_counts = Counter()
        self.bucket_products: dict[str, set[str]] = defaultdict(set)
        self.anchors: dict[str, dict[float, dict[str, Any]]] = defaultdict(dict)

    @staticmethod
    def bucket(p: float) -> str:
        if p < .2: return "<0.20"
        if p < .3: return "0.20-0.30"
        if p < .5: return "0.30-0.50"
        if p < .7: return "0.50-0.70"
        if p < .8: return "0.70-0.80"
        return ">=0.80"

    def add(self, record: Mapping[str, Any]):
        pid = str(record["sealedProductId"])
        key = (int(record["quantity"]), int(record["priceCents"]))
        if key in self.seen[pid]:
            return
        self.seen[pid].add(key)
        p = float(record["chanceToRecoverCapital"])
        bucket = self.bucket(p)
        self.bucket_counts[bucket] += 1
        self.bucket_products[bucket].add(pid)
        for name, value in (
            ("pWin", p), ("typical", record["typicalRetentionScore"]),
            ("shortfall", record["shortfallResilienceScore"]),
            ("bee", record["baseEconomicEfficiencyScore"]),
            ("v4", record["financialRipV4Score"]),
            ("v5", record["financialRipV5CandidateScore"]),
            ("priceCents", record["priceCents"]),
            ("quantity", record["quantity"]),
            ("p50Value", record["p50Value"]),
            ("loss", record["lossResilienceScore"]),
            ("trueWin", record["trueWinFrequencyScore"]),
            ("overallV12", record["overallRipV12Score"]),
            ("overallV5", record["overallRipFinancialV5ShadowScore"]),
            ("committedCapital", record["actualCommittedCapital"]),
        ):
            self.columns[name].append(float(value))
        for target in (0, .2, .3, .5, .7, .8, .9, 1):
            existing = self.anchors[pid].get(target)
            if existing is None or abs(p - target) < abs(float(existing["chanceToRecoverCapital"]) - target):
                self.anchors[pid][target] = {k: record.get(k) for k in (
                "sealedProductId", "quantity", "priceCents", "actualCommittedCapital",
                "chanceToRecoverCapital", "financialRipV4Score", "financialRipV5CandidateScore",
                "overallRipV12Score", "overallRipFinancialV5ShadowScore", "typicalRetentionScore",
                "trueWinFrequencyScore", "lossResilienceScore", "shortfallResilienceScore",
                "baseEconomicEfficiencyScore", "cappedRecovery", "p95Value",
                "p50Value")}

    def summary(self) -> dict[str, Any]:
        a = {key: np.asarray(values, dtype=np.float64) for key, values in self.columns.items()}
        def corr(mask, x, y):
            xx, yy = a[x][mask], a[y][mask]
            if len(xx) < 3 or np.std(xx) == 0 or np.std(yy) == 0:
                return None
            return {"pearson": float(pearsonr(xx, yy).statistic),
                    "spearman": float(spearmanr(xx, yy).statistic)}
        p = a["pWin"]
        masks = {"all": np.ones(len(p), dtype=bool), "<0.20": p < .2,
                 "0.20-0.50": (p >= .2) & (p < .5), ">=0.50": p >= .5}
        return {"distinctCandidatePrices": len(p),
                "bucketEvaluations": dict(self.bucket_counts),
                "bucketProductCounts": {k: len(v) for k, v in self.bucket_products.items()},
                "correlationSampleCounts": {name: int(np.count_nonzero(mask))
                                            for name, mask in masks.items()},
                "correlations": {name: {"srTypical": corr(mask, "shortfall", "typical"),
                                        "srPWin": corr(mask, "shortfall", "pWin"),
                                        "srBEE": corr(mask, "shortfall", "bee")}
                                 for name, mask in masks.items()},
                "productsAtOrAbove": {str(t): sum(any(float(r["chanceToRecoverCapital"]) >= t
                    for r in anchors.values()) for anchors in self.anchors.values())
                    for t in (.3, .5, .7, .8)},
                "productIdsAtOrAbove": {str(t): sorted(pid for pid, anchors in self.anchors.items()
                    if any(float(r["chanceToRecoverCapital"]) >= t for r in anchors.values()))
                    for t in (.3, .5, .7, .8)},
                "trajectoryAnchors": {pid: list(anchors.values()) for pid, anchors in self.anchors.items()}}

    def restore(self, checkpoint: Mapping[str, Any], directory: Path) -> None:
        self.bucket_counts.update(checkpoint.get("bucketCounts", {}))
        for bucket, products in checkpoint.get("bucketProducts", {}).items():
            self.bucket_products[bucket].update(products)
        for pid, anchors in checkpoint.get("anchors", {}).items():
            self.anchors[pid] = {float(key): value for key, value in anchors.items()}
        for name in checkpoint.get("trajectoryFiles", []):
            with np.load(directory / name) as saved:
                for key in self.columns:
                    self.columns[key].extend(saved[key])

    def checkpoint_metadata(self, files: list[str]) -> dict[str, Any]:
        return {
            "bucketCounts": dict(self.bucket_counts),
            "bucketProducts": {key: sorted(value) for key, value in self.bucket_products.items()},
            "anchors": {pid: {str(key): value for key, value in anchors.items()}
                        for pid, anchors in self.anchors.items()},
            "trajectoryFiles": files,
        }


class PreparedV5Candidate(PreparedCanonicalCandidate):
    collector: PriceCollector | None = None

    def score_candidate(self, price_cents: int) -> dict[str, Any]:
        score_started = time.perf_counter()
        cache = self.__dict__.setdefault("_research_score_cache", OrderedDict())
        if price_cents in cache:
            cache.move_to_end(price_cents)
            return dict(cache[price_cents])
        unit_price = price_cents / 100.0
        capital = self.quantity * unit_price
        kwargs = {} if not self.min_simulation_count else {
            "min_simulation_count": self.min_simulation_count}
        v3 = self.distribution.score(capital, **kwargs)
        projected_v4 = project_financial_rip_v4_from_v3_payload(v3)
        v12 = compute_overall_rip_v12(
            projected_v4.get("score"), self.chase_accessibility_raw,
            self.collector_appeal_score)
        raw = {key: record.get("raw") for key, record in
               ((v3.get("audit") or {}).get("normalizedInputs") or {}).items()}
        control = {
            "sealedProductId": self.product_id, "priceCents": price_cents,
            "quantity": self.quantity, "targetBudget": self.target_budget,
            "actualCommittedCapital": capital,
            "financialRipV3Score": v3.get("score"),
            "financialRipV4Score": projected_v4.get("score"),
            "overallRipV12Score": v12.get("score"),
            "overallRipV12Rankable": bool(v12.get("rankable")),
            "chanceToRecoverCapital": raw.get("true_win_probability"),
        }
        v4, v5 = score_financial_rip_v5_candidate_with_control(
            self.distribution, capital, min_simulation_count=self.min_simulation_count or 10000,
            control_payload=projected_v4,
        )
        if v5["status"] != "ready":
            raise ValueError("V5 candidate unavailable at scored price")
        c = v5["components"]
        record = {**control,
                  "financialRipV5CandidateScore": v5["score"],
                  "overallRipFinancialV5ShadowScore": overall_shadow(
                      v5["score"], self.chase_accessibility_raw, self.collector_appeal_score),
                  "overallShadowVersion": OVERALL_SHADOW_ID,
                  "typicalRetentionScore": c["typical_retention"]["score"],
                  "trueWinFrequencyScore": c["true_win_frequency"]["score"],
                  "lossResilienceScore": v4["components"]["loss_resilience"]["score"],
                  "shortfallResilienceScore": c["shortfall_resilience"]["score"],
                  "baseEconomicEfficiencyScore": c["base_economic_efficiency"]["score"],
                  "cappedRecovery": c["shortfall_resilience"]["raw"]["cappedRecovery"],
                  "p50Value": v3["distributionDisclosures"]["medianValue"],
                  "p95Value": v5["components"]["realistic_upside"]["raw"].get("p95ThresholdValue")}
        record["scoringSeconds"] = time.perf_counter() - score_started
        if self.collector is not None:
            self.collector.add(record)
        cache[price_cents] = record
        if len(cache) > 4096:
            cache.popitem(last=False)
        return record

    def compare(self, score_record: Mapping[str, Any], benchmark: Mapping[str, Any], *, authority: str) -> bool:
        comparator_started = time.perf_counter()
        if authority == FINANCIAL_V5:
            wins = financial_v5_key(score_record) < financial_v5_key(benchmark)
        elif authority == OVERALL_V5:
            wins = overall_v5_key(score_record) < overall_v5_key(benchmark)
        else:
            return super().compare(score_record, benchmark, authority=authority)
        self._last_comparator_seconds = time.perf_counter() - comparator_started
        return wins

    def evaluate(self, price_cents: int, benchmark: Mapping[str, Any], *, comparison_authority: str) -> dict[str, Any]:
        record = dict(self.score_candidate(price_cents))
        return {**record, "wins": self.compare(record, benchmark, authority=comparison_authority),
                "comparisonAuthority": comparison_authority, "comparatorSeconds": 0.0}


def current_rankings(source_rows, prompt2_rows, budget):
    source_by_id = {str(r["sealed_product_id"]): r for r in source_rows}
    ranked = []
    for prior in prompt2_rows:
        pid = prior["sealedProductId"]
        source = source_by_id[pid]
        row = {"sealedProductId": pid, "financialRipV4Score": prior["v4Score"],
               "financialRipV5CandidateScore": prior["v5Score"],
               "overallRipV12Score": float(source["overall_rip_v12_score"]),
               "overallRipFinancialV5ShadowScore": overall_shadow(
                   prior["v5Score"], float(source["chase_accessibility_raw"]),
                   float(source["collector_appeal_score"])),
               "chanceToRecoverCapital": prior["pWin"],
               "actualCommittedCapital": float(source["actual_committed_capital"]),
               "targetBudget": budget}
        ranked.append(row)
    fin = sorted(ranked, key=financial_v5_key)
    overall = sorted(ranked, key=overall_v5_key)
    return ranked, fin, overall


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


CHECKPOINT_AUTHORITY_FIELDS = (
    "sourceSnapshotId", "sourceFingerprint", "sourceAuthorityFingerprint",
    "candidateVersion", "overallShadowVersion", "searchMethodIdentity",
)


def load_matching_checkpoint(path: Path, authority: Mapping[str, Any]) -> dict[str, Any]:
    previous = json.loads(path.read_text(encoding="utf-8"))
    for key in CHECKPOINT_AUTHORITY_FIELDS:
        if previous.get(key) != authority.get(key):
            raise RuntimeError(f"checkpoint authority mismatch: {key}")
    return previous


def control_complete_for_candidate(control: Mapping[str, Any] | None,
                                   candidate: Mapping[str, Any], count: int) -> bool:
    if not control or control.get("status") != "complete" or len(control.get("products", [])) != count:
        return False
    for key in ("sourceSnapshotId", "sourceFingerprint", "sourceAuthorityFingerprint"):
        if control.get(key) != candidate.get(key):
            raise RuntimeError(f"completed control authority differs from candidate: {key}")
    return True


def run(product_limit: int = 0, start_rank: int = 1, *, resume: bool = False,
        restart: bool = False, checkpoint: Path = CHECKPOINT,
        product_id: str | None = None):
    if resume and restart:
        raise ValueError("resume and restart are mutually exclusive")
    client = get_client()
    snapshots = client.table("budget_product_ranking_snapshots").select("*").eq(
        "publication_status", "published").order("created_at", desc=True).limit(1).execute().data
    if not snapshots:
        raise RuntimeError("no published Full Market snapshot")
    snapshot_id = str(snapshots[0]["id"])
    snapshot, source_rows, all_rows = _load_source(client, snapshot_id)
    validate_source(snapshot)
    validate_rank_column_contiguous(source_rows, "budget_rank_v12")
    validate_rank_column_contiguous(source_rows, "financial_only_rank")
    validate_financial_only_rank_reconstructs(source_rows)
    _verify_v12_parity(all_rows, label="V5 shadow whole snapshot")
    authority = _historical_authority(snapshot, source_rows)
    products = _load_exact_source_products(client, source_rows, str(snapshot["pinned_price_as_of"]))
    if cohort_fingerprint(products, str(snapshot["pinned_price_as_of"])) != snapshot["cohort_fingerprint"]:
        raise RuntimeError("current cohort fingerprint mismatch")
    prompt2 = json.loads(PROMPT2.read_text(encoding="utf-8"))["states"][0]
    if prompt2["snapshot"]["id"] != snapshot_id or prompt2["snapshot"]["cohort_fingerprint"] != snapshot["cohort_fingerprint"]:
        raise RuntimeError("Prompt 2 cohort authority changed; current V5 rankings must be rescored")
    budget = float(snapshot["full_market_budget"])
    current, fin_ranked, overall_ranked = current_rankings(source_rows, prompt2["rows"], budget)
    financial_rank = {r["sealedProductId"]: i for i, r in enumerate(fin_ranked, 1)}
    overall_rank = {r["sealedProductId"]: i for i, r in enumerate(overall_ranked, 1)}
    by_id = {r["sealedProductId"]: r for r in current}
    source_by_id = {str(r["sealed_product_id"]): r for r in source_rows}
    collector = PriceCollector()
    output = {"sourceSnapshotId": snapshot_id, "sourceFingerprint": snapshot["cohort_fingerprint"],
              "sourceAuthorityFingerprint": authority["fingerprint"], "budget": budget,
              "candidateVersion": CANDIDATE_ID, "overallShadowVersion": OVERALL_SHADOW_ID,
              "controlMethodVersion": BEST_OPEN_PRICE_V2_METHOD_VERSION,
              "currentRankings": {"financialV5": [r["sealedProductId"] for r in fin_ranked],
                                  "overallV5Shadow": [r["sealedProductId"] for r in overall_ranked]},
              "searchMethodIdentity": "fused_v2_exact_cent_single_q_parity_batch_v2_trajectory",
              "products": []}
    if resume:
        output = load_matching_checkpoint(checkpoint, output)
    elif checkpoint.exists() and not restart:
        raise RuntimeError("checkpoint exists; specify --resume or --restart")
    completed = {row["sealedProductId"] for row in output["products"]}
    if resume:
        collector.restore(output.get("collectorCheckpoint", {}), checkpoint.parent)
    trajectory_files = list(output.get("collectorCheckpoint", {}).get("trajectoryFiles", []))
    ordered = sorted(source_rows, key=lambda r: int(r["budget_rank_v12"]))
    if product_id:
        ordered = [row for row in ordered if str(row["sealed_product_id"]) == product_id]
        if not ordered:
            raise ValueError("requested product is absent from frozen cohort")
    ordered = ordered[start_rank - 1:]
    if product_limit:
        ordered = ordered[:product_limit]
    for i, source in enumerate(ordered, 1):
        pid = str(source["sealed_product_id"])
        if pid in completed:
            continue
        column_start = len(collector.columns["pWin"])
        product = next(p for p in products if str(p["sealed_product_id"]) == pid)
        run_id = str(source["source_calculation_run_id"])
        artifact = load_pack_outcome_artifact(client, run_id)
        base = build_stage1_distributions_cached(artifact,
            int(product.get("random_pack_count") or product["pack_count"]), run_id)
        @lru_cache(maxsize=8)
        def factory(q: int):
            values = build_budget_strategy_values(
                base_random_pack_values=base, quantity=q,
                guaranteed_component_market_value=None,
                canonical_set_key=f"budget:{pid}", run_fingerprint=None)
            prepared = PreparedFinancialRipDistribution.prepare(values,
                value_offset=float(product.get("guaranteed_component_market_value") or 0) * q)
            candidate = PreparedV5Candidate(pid, q, prepared,
                float(source["collector_appeal_score"]),
                float(authority["rawBySet"][str(source["set_id"])]), budget)
            candidate.collector = collector
            return candidate
        def batch_factory(quantities):
            built = build_single_q_parity_distributions(
                base, quantities=quantities, canonical_set_key=f"budget:{pid}",
                run_fingerprint=None)
            batch = {}
            for q in quantities:
                values = built["distributions"].pop(q)
                prepared = PreparedFinancialRipDistribution.prepare(values,
                    value_offset=float(product.get("guaranteed_component_market_value") or 0) * q)
                candidate = PreparedV5Candidate(pid, q, prepared,
                    float(source["collector_appeal_score"]),
                    float(authority["rawBySet"][str(source["set_id"])]), budget)
                candidate.collector = collector
                batch[q] = candidate
            return batch
        benchmarks = {
            FINANCIAL_V5: fin_ranked[1] if financial_rank[pid] == 1 else fin_ranked[0],
            OVERALL_V5: overall_ranked[1] if overall_rank[pid] == 1 else overall_ranked[0],
        }
        ranks = {FINANCIAL_V5: financial_rank[pid], OVERALL_V5: overall_rank[pid]}
        width = single_q_parity_batch_width(len(base), requested_width=8,
            maximum_quantity=min(4096, round(budget * 100)))
        search = DualBestOpenPriceSearch(
            product_id=pid, budget_cents=round(budget * 100),
            current_price_cents=round(float(source["product_market_price"]) * 100),
            current_quantity=int(source["quantity"]),
            rip_current_rank=ranks[OVERALL_V5], rip_benchmark=benchmarks[OVERALL_V5],
            financial_current_rank=ranks[FINANCIAL_V5],
            financial_benchmark=benchmarks[FINANCIAL_V5],
            prepare_quantity=factory, prepare_quantities=batch_factory,
            source_authority_fingerprint=authority["fingerprint"],
            expected_source_authority_fingerprint=authority["fingerprint"],
            rip_comparison_authority=OVERALL_V5,
            financial_comparison_authority=FINANCIAL_V5,
            quantity_batch_size=width, enable_quantity_prefetch=True,
            rng_outcome_count=len(base),
        )
        rss_sampler = _RssSampler()
        rss_sampler.start()
        try:
            fused = search.search()
        finally:
            rss_sampler.stop()
        axis_results = {FINANCIAL_V5: fused["financialResult"],
                        OVERALL_V5: fused["ripResult"]}
        output["products"].append({"sealedProductId": pid, "productName": product.get("product_name"),
                                    "setId": str(source["set_id"]), "family": source["product_family"],
                                    "sourceRunId": run_id, "artifactSha256": artifact.metadata["raw_sha256"],
                                    "currentPriceCents": round(float(source["product_market_price"]) * 100),
                                    "currentQuantity": int(source["quantity"]),
                                    "currentFinancialV5Rank": financial_rank[pid],
                                    "currentOverallV5Rank": overall_rank[pid],
                                    "financialV5": axis_results[FINANCIAL_V5],
                                    "overallV5Shadow": axis_results[OVERALL_V5],
                                    "fusedDiagnostics": {**fused["diagnostics"],
                                        "requestedQuantityBatchWidth": 8,
                                        "effectiveQuantityBatchWidth": width,
                                        "peakRssBytes": rss_sampler.peak_rss_bytes}})
        trajectory_name = f"{checkpoint.stem}_trajectory_{pid}.npz"
        trajectory_path = checkpoint.parent / trajectory_name
        temporary = trajectory_path.with_name(trajectory_name + "." + uuid.uuid4().hex + ".tmp")
        with temporary.open("wb") as handle:
            np.savez(handle, **{key: np.asarray(value[column_start:], dtype=np.float64)
                                 for key, value in collector.columns.items()})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, trajectory_path)
        trajectory_files.append(trajectory_name)
        output["collectorCheckpoint"] = collector.checkpoint_metadata(trajectory_files)
        atomic_json(checkpoint, output)
        collector.seen.pop(pid, None)
        print(f"candidate thresholds {i}/{len(ordered)}: {product.get('product_name')}", flush=True)
    if len(output["products"]) == len(source_rows):
        output["candidatePriceDomain"] = collector.summary()
        control = json.loads(CONTROL_OUTPUT.read_text(encoding="utf-8")) if CONTROL_OUTPUT.exists() else None
        if control_complete_for_candidate(control, output, len(source_rows)):
            atomic_json(OUTPUT, output)
            print(f"wrote {OUTPUT}")
        else:
            atomic_json(checkpoint, output)
            print(f"candidate complete; waiting for full control at {checkpoint}")
    else:
        print(f"checkpointed {len(output['products'])}/{len(source_rows)} products at {checkpoint}")
    return output


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--product-limit", type=int, default=0)
    p.add_argument("--start-rank", type=int, default=1)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--restart", action="store_true")
    p.add_argument("--product-id")
    p.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    args = p.parse_args()
    run(args.product_limit, args.start_rank, resume=args.resume, restart=args.restart,
        product_id=args.product_id, checkpoint=args.checkpoint)
