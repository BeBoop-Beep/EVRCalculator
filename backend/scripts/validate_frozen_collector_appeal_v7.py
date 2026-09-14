"""Validate the frozen Collector Appeal V7 candidate against price outcomes.

This is a read-only research entry point. It never writes Collector tables, changes
the current pointer, or feeds price-derived coefficients back into scoring.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, Mapping, Sequence

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.research.collector_appeal_market_validation import (  # noqa: E402
    ComponentSpec, compare_components,
)
from backend.research.collector_appeal_market_validation.stats import (  # noqa: E402
    DEFAULT_CONTROLS, pearson, run_component_suite, spearman,
)
from backend.scripts.research_collector_appeal_market_validation import (  # noqa: E402
    canonical_hash, extract_market_cohort,
)

MODEL_RUN_ID = "e282f26e-2136-4105-b0a3-f0974c4d9d70"
MODEL_VERSION = "pokemon_collector_appeal_v7_expanded_price_blind_v1"
MODEL_FINGERPRINT = "3b781f4ec01ef8c74c77b34d2b91e9a90231d2feccf2ee41411de64606378c9d"
CARD_FINGERPRINT = "7dbe5e989c6eb7bcb9d4684707f9c239ab1ca701fc429a7a0605657d79f2ab90"
SET_FINGERPRINT = "744f088e7e1e33e5f8b40aca707b8f7e0d93bf7def8308b860da0277257a4b52"
V6_RUN_ID = "84833101-e658-49ea-82e2-033f7d4d8e09"
V6_VERSION = "pokemon_collector_appeal_v6_corrected_complete_trends_v2"
CONTRACT = "collector_appeal_v7_frozen_price_validation_v1"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen_artifact(payload: Mapping[str, Any]) -> Dict[str, Any]:
    manifest = payload.get("manifest") or {}
    expected = {
        "modelVersion": MODEL_VERSION, "modelFingerprint": MODEL_FINGERPRINT,
        "cardFingerprint": CARD_FINGERPRINT, "setFingerprint": SET_FINGERPRINT,
    }
    mismatches = {k: {"expected": v, "actual": manifest.get(k)} for k, v in expected.items()
                  if manifest.get(k) != v}
    def keys(value: Any) -> Iterable[str]:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                yield str(key).casefold()
                yield from keys(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from keys(nested)
    config_keys = set(keys(manifest.get("config") or {}))
    prohibited = sorted(config_keys & {"market_price", "sales", "auction_count", "portfolio_value"})
    if mismatches or prohibited or len(payload.get("cards") or []) != 18293:
        raise RuntimeError(f"V7_VALIDATION_MODEL_MUTATION_BLOCKER: {mismatches=} {prohibited=}")
    return {"verified": True, "expected": expected, "configFingerprint": canonical_hash(manifest["config"]),
            "sourceRunIds": manifest.get("sourceRunIds"), "cardRows": len(payload["cards"]),
            "setRows": len(payload.get("sets") or [])}


def component_specs() -> list[ComponentSpec]:
    return [
        ComponentSpec("pokemon_subject", "pokemon_subject_appeal", ("pokemon",)),
        ComponentSpec("trainer_subject", "trainer_appeal", ("trainer",)),
        ComponentSpec("artist", "artist_appeal", ("pokemon", "trainer"), cross_bucket_comparable=True),
        ComponentSpec("playability_lift", "playability_lift", ("pokemon",)),
        ComponentSpec("card_appeal_v6", "card_appeal_v6", ("pokemon", "trainer"), role="final", cross_bucket_comparable=True),
        ComponentSpec("card_appeal_v7", "card_appeal_v7", ("pokemon", "trainer"), role="final", cross_bucket_comparable=True),
    ]


def join_rows(market: Mapping[str, Any], frozen: Mapping[str, Any]) -> tuple[list[dict[str, Any]], Dict[str, Any]]:
    cards = {str(row["canonical_card_id"]): row for row in frozen["cards"]}
    joined = []
    for source in market.get("rows") or []:
        card = cards.get(str(source.get("card_id") or ""))
        if not card:
            continue
        subject = str(card.get("subject_type") or "").casefold()
        row = dict(source)
        row.update({
            "canonical_card_id": card["canonical_card_id"], "subject_type": subject,
            "subject_cluster_key": card.get("subject_identity"),
            "pokemon_subject_appeal": card.get("subject_appeal_corrected") if subject == "pokemon" else None,
            "trainer_appeal": card.get("subject_appeal_corrected") if subject == "trainer" else None,
            "subject_appeal": card.get("subject_appeal_corrected"),
            "artist_appeal": card.get("artist_appeal_score"),
            "artist_status": card.get("artist_evidence_status"),
            "playability_lift": card.get("applied_lift_corrected"),
            "card_appeal_v6": card.get("card_collector_appeal_corrected"),
            "card_appeal_v7": card.get("card_collector_appeal_v7"),
            "v7_increment_over_v6": (float(card["card_collector_appeal_v7"]) - float(card["card_collector_appeal_corrected"]))
                if card.get("card_collector_appeal_v7") is not None and card.get("card_collector_appeal_corrected") is not None else None,
            "artist_name": (card.get("artist_names") or [None])[0],
        })
        joined.append(row)
    return joined, {"marketRows": len(market.get("rows") or []), "joinedRows": len(joined),
                    "unmatchedMarketRows": len(market.get("rows") or []) - len(joined),
                    "frozenRowsOutsideControlledCohort": len(cards) - len(joined),
                    "joinKey": "exact canonical card UUID"}


def raw_within_set(rows: Sequence[Mapping[str, Any]], key: str, min_n: int = 8) -> Dict[str, Any]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get(key) is not None:
            groups[str(row["set_id"])].append(row)
    results = []
    for set_id, subset in sorted(groups.items()):
        if len(subset) < min_n:
            continue
        x = [r[key] for r in subset]; lp = [r["log_price"] for r in subset]
        results.append({"setId": set_id, "setName": subset[0].get("set_name"), "era": subset[0].get("era"),
                        "n": len(subset), "spearmanPrice": spearman(x, [r["market_price"] for r in subset]),
                        "spearmanLogPrice": spearman(x, lp), "pearsonLogPrice": pearson(x, lp)})
    rhos = [r["spearmanLogPrice"] for r in results if r["spearmanLogPrice"] is not None]
    weights = [r["n"] for r in results if r["spearmanLogPrice"] is not None]
    return {"component": key, "minimumSetN": min_n, "sets": results,
            "summary": {"sets": len(rhos), "medianRho": float(np.median(rhos)) if rhos else None,
                        "weightedMeanRho": float(np.average(rhos, weights=weights)) if rhos else None,
                        "positivePct": 100 * sum(v > 0 for v in rhos) / len(rhos) if rhos else None,
                        "materiallyPositivePct": 100 * sum(v >= .2 for v in rhos) / len(rhos) if rhos else None,
                        "negativePct": 100 * sum(v < 0 for v in rhos) / len(rhos) if rhos else None}}


def coverage(rows: Sequence[Mapping[str, Any]], frozen_count: int) -> list[dict[str, Any]]:
    cohorts = {
        "ALL frozen eligible cards": lambda r: True,
        "ALL priced cards in exact-scarcity sets": lambda r: True,
        "Pokemon Appeal available": lambda r: r.get("pokemon_subject_appeal") is not None,
        "Trainer Appeal available": lambda r: r.get("trainer_appeal") is not None,
        "Artist Appeal available": lambda r: r.get("artist_appeal") is not None,
        "Pull Scarcity available": lambda r: r.get("pull_scarcity") is not None,
        "Treatment available": lambda r: r.get("treatment_prestige") is not None,
        "Appeal + Scarcity + Treatment": lambda r: r.get("card_appeal_v7") is not None and r.get("pull_scarcity") is not None and r.get("treatment_prestige") is not None,
    }
    out = []
    for name, predicate in cohorts.items():
        subset = list(rows) if name != "ALL frozen eligible cards" else []
        if name == "ALL frozen eligible cards":
            out.append({"cohort": name, "n": frozen_count, "sets": 128, "missingFromFrozen": 0}); continue
        subset = [r for r in rows if predicate(r)]
        out.append({"cohort": name, "n": len(subset), "sets": len({r["set_id"] for r in subset}),
                    "eras": len({r.get("era") for r in subset}), "missingFromFrozen": frozen_count-len(subset)})
    return out


def matched_analysis(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    groups: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["set_id"], row.get("rarity_key"), row.get("slot_group"), row.get("is_secret"),
                row.get("is_promo"), row.get("is_mechanic_card"))].append(row)
    pairs = []
    for cohort in groups.values():
        ordered = sorted(cohort, key=lambda r: float(r["card_appeal_v7"]))
        if len(ordered) < 2:
            continue
        low, high = ordered[0], ordered[-1]
        if float(high["card_appeal_v7"]) - float(low["card_appeal_v7"]) < 10:
            continue
        if abs(float(high["pull_scarcity"]) - float(low["pull_scarcity"])) > .05:
            continue
        pairs.append((low, high))
    ratios = [float(h["market_price"])/float(l["market_price"]) for l,h in pairs]
    return {"policy": "same set/rarity/slot/promo/secret/mechanic; scarcity delta <=0.05; Appeal delta >=10",
            "pairCount": len(pairs), "higherAppealWinRate": sum(v > 1 for v in ratios)/len(ratios) if ratios else None,
            "medianPriceRatio": float(np.median(ratios)) if ratios else None,
            "medianAppealDelta": float(np.median([h["card_appeal_v7"]-l["card_appeal_v7"] for l,h in pairs])) if pairs else None}


def redundancy(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    def pair(a: str, b: str) -> Dict[str, Any]:
        sample = [r for r in rows if r.get(a) is not None and r.get(b) is not None]
        return {"n": len(sample), "spearman": spearman([r[a] for r in sample], [r[b] for r in sample]),
                "pearson": pearson([r[a] for r in sample], [r[b] for r in sample])}
    return {"artistVsSubject": pair("artist_appeal", "subject_appeal"),
            "scarcityVsTreatment": pair("pull_scarcity", "treatment_prestige"),
            "scarcityVsV7": pair("pull_scarcity", "card_appeal_v7")}


def sensitivity(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    prices = np.asarray([float(r["market_price"]) for r in rows])
    outputs = []
    for label, cutoff in (("full", None), ("exclude_top_1_pct", 99), ("exclude_top_5_pct", 95)):
        sample = list(rows) if cutoff is None else [r for r in rows if float(r["market_price"]) <= np.percentile(prices, cutoff)]
        outputs.append({"sample": label, "n": len(sample), "spearman": spearman([r["card_appeal_v7"] for r in sample], [r["log_price"] for r in sample]),
                        "withinSet": raw_within_set(sample, "card_appeal_v7")["summary"]})
    return outputs


def residual_price_test(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Residualize log price on within-set structural controls, then test V7."""
    controls = ("pull_scarcity", "treatment_prestige", "log_release_age", "is_secret",
                "is_promo", "is_mechanic_card", "is_stage2", "is_trainer")
    sample = [r for r in rows if r.get("card_appeal_v7") is not None and all(r.get(k) is not None for k in controls)]
    groups = np.asarray([str(r["set_id"]) for r in sample])
    x = np.asarray([[float(r[k]) for k in controls] for r in sample]); y = np.asarray([float(r["log_price"]) for r in sample])
    appeal = np.asarray([float(r["card_appeal_v7"]) for r in sample])
    for group in sorted(set(groups)):
        mask = groups == group; x[mask] -= x[mask].mean(axis=0); y[mask] -= y[mask].mean(); appeal[mask] -= appeal[mask].mean()
    keep = np.std(x, axis=0) > 1e-10; x = x[:, keep]
    beta, *_ = np.linalg.lstsq(x, y, rcond=None); residual = y - x @ beta
    slope = float(np.linalg.lstsq(appeal.reshape(-1, 1), residual, rcond=None)[0][0])
    return {"n": len(sample), "sets": len(set(groups)), "spearman": spearman(appeal, residual),
            "pearson": pearson(appeal, residual), "slopePerAppealPoint": slope,
            "controls": list(controls), "setFixedEffects": "within-set demeaning"}


def price_quality(client: Any, frozen_ids: set[str], stale_days: int = 45) -> Dict[str, Any]:
    rows = []
    start = 0
    while True:
        page = client.table("pokemon_canonical_card_market_prices_latest").select(
            "canonical_card_id,market_price,captured_at,source,condition_id,printing_type,price_selection_reason"
        ).range(start, start + 999).execute().data or []
        rows.extend(r for r in page if str(r.get("canonical_card_id")) in frozen_ids)
        if len(page) < 1000: break
        start += 1000
    today = datetime.now(timezone.utc).date()
    dates = [date.fromisoformat(str(r["captured_at"])) for r in rows if r.get("captured_at")]
    ids = [str(r.get("canonical_card_id")) for r in rows]
    return {"eligibleCards": len(frozen_ids), "cardsWithCurrentPrice": len(set(ids)),
            "missingPriceCount": len(frozen_ids-set(ids)), "zeroOrInvalidPriceCount": sum(not r.get("market_price") or float(r["market_price"]) <= 0 for r in rows),
            "duplicateAuthorityConflicts": len(ids)-len(set(ids)), "staleThresholdDays": stale_days,
            "stalePriceCount": sum((today-d).days > stale_days for d in dates),
            "observationDate": {"min": min(dates).isoformat() if dates else None, "max": max(dates).isoformat() if dates else None,
                                "distribution": dict(sorted(Counter(d.isoformat() for d in dates).items()))},
            "sources": dict(Counter(str(r.get("source")) for r in rows)),
            "normalization": "canonical latest view: one canonical card, accepted condition/printing selected by price_selection_reason"}


def verdict(summary: Mapping[str, Any], direct_increment: Mapping[str, Any]) -> tuple[str, str]:
    v7 = next(r for r in summary["component_summary"] if r["component"] == "card_appeal_v7")
    v6 = next(r for r in summary["component_summary"] if r["component"] == "card_appeal_v6")
    gain = v7.get("incremental_r2_gain_vs_scarcity") or 0.0
    raw = v7.get("raw_spearman_vs_log_price") or 0.0
    direct = (direct_increment.get("incremental_lift_out_of_sample") or {}).get("component_over_scarcity_M3_vs_M2") or {}
    direct_gain = direct.get("r2_gain") or 0.0
    if raw > .2 and gain > .005 and direct_gain > .005:
        return "APPEAL_PRICING_SIGNAL_STRONG", "V7_PROMOTION_SUPPORTED"
    if raw > .1 and gain > 0 and direct_gain > 0:
        return "APPEAL_PRICING_SIGNAL_PARTIAL", "V7_PROMOTION_SUPPORTED_WITH_LIMITATIONS"
    if raw > 0:
        return "APPEAL_PRICING_SIGNAL_WEAK", "V7_PROMOTION_NOT_SUPPORTED"
    return "APPEAL_PRICING_SIGNAL_NOT_SUPPORTED", "V7_PROMOTION_NOT_SUPPORTED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen-artifact", type=Path, default=ROOT/"backend/artifacts/collector_appeal_v7_expanded_candidate_v1.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT/"docs/research/collector_appeal_v7_price_validation")
    parser.add_argument("--bootstrap-draws", type=int, default=200)
    args = parser.parse_args()
    frozen = read_json(args.frozen_artifact); before_hash = file_sha256(args.frozen_artifact)
    freeze = verify_frozen_artifact(frozen)
    load_dotenv(ROOT/"backend/.env", override=False)
    from backend.db.clients.supabase_client import service_read_client
    client = service_read_client
    market = extract_market_cohort(client)
    rows, join = join_rows(market, frozen)
    quality = price_quality(client, {str(r["canonical_card_id"]) for r in frozen["cards"]})
    if quality["zeroOrInvalidPriceCount"] or quality["duplicateAuthorityConflicts"]:
        raise RuntimeError("V7_PRICE_OUTCOME_QUALITY_BLOCKER")
    analysis = compare_components(rows, component_specs(), bootstrap_draws=args.bootstrap_draws)
    direct_increment = run_component_suite(
        rows, ComponentSpec("v7_increment_after_v6", "v7_increment_over_v6", ("pokemon", "trainer"),
                            cross_bucket_comparable=True),
        controls=DEFAULT_CONTROLS + ("card_appeal_v6",), bootstrap_draws=args.bootstrap_draws,
    )
    artist_after_subject = run_component_suite(
        rows, ComponentSpec("artist_after_subject", "artist_appeal", ("pokemon", "trainer"),
                            cross_bucket_comparable=True),
        controls=DEFAULT_CONTROLS + ("subject_appeal",), bootstrap_draws=args.bootstrap_draws,
    )
    playability_after_subject = run_component_suite(
        rows, ComponentSpec("playability_after_subject", "playability_lift", ("pokemon",)),
        controls=DEFAULT_CONTROLS + ("subject_appeal",), bootstrap_draws=args.bootstrap_draws,
    )
    within = {key: raw_within_set(rows, key) for key in ("card_appeal_v6", "card_appeal_v7")}
    master = {"contractVersion": CONTRACT, "generatedAt": datetime.now(timezone.utc).isoformat(),
              "frozenModel": {**freeze, "artifactSha256Before": before_hash}, "priceQuality": quality,
              "dataset": {"marketManifest": {k:v for k,v in market.items() if k != "rows"}, "join": join,
                          "coverage": coverage(rows, len(frozen["cards"])), "rowFingerprint": canonical_hash(rows)},
              "analysis": analysis, "directV7AfterV6": direct_increment,
              "artistAfterSubject": artist_after_subject, "playabilityAfterSubject": playability_after_subject,
              "withinSet": within, "residualPrice": residual_price_test(rows), "matchedCards": matched_analysis(rows),
              "redundancy": redundancy(rows), "sensitivity": sensitivity(rows),
              "crossEra": {"status": "EXPLORATORY_CROSS_ERA_ONLY", "limitations": ["surviving supply attrition", "historical significance", "vintage premium", "collection lock-up", "grading population", "sealed-product scarcity", "nostalgia formation"]}}
    overall, promotion = verdict(analysis, direct_increment)
    master["decision"] = {"overallPricingVerdict": overall, "promotionRecommendation": promotion,
                          "v7Mutated": False, "productionMutations": "NONE"}
    after_hash = file_sha256(args.frozen_artifact)
    master["frozenModel"]["artifactSha256After"] = after_hash
    if after_hash != before_hash: raise RuntimeError("V7_VALIDATION_MODEL_MUTATION_BLOCKER")
    out = args.output_dir
    write_json(out/"master_result.json", master)
    artifacts = {
        "frozen_dataset_manifest.json": master["dataset"], "coverage_table.json": master["dataset"]["coverage"],
        "within_set_results.json": within, "within_era_results.json": {k:v["by_era"] for k,v in analysis["components"].items()},
        "exploratory_cross_era_results.json": master["crossEra"],
        "v6_vs_v7_comparison.json": {"parallel": [r for r in analysis["component_summary"] if r["component"] in {"card_appeal_v6","card_appeal_v7"}], "directIncrementAfterV6": direct_increment},
        "component_results.json": analysis["component_summary"],
        "artist_incremental_analysis.json": {"unadjustedForSubject": analysis["components"]["artist"], "afterSubject": artist_after_subject},
        "interaction_analysis.json": {k:v["incremental_lift_out_of_sample"].get("interaction_over_additive_M4_vs_M3") for k,v in analysis["components"].items()},
        "robustness_sensitivity.json": master["sensitivity"], "promotion_recommendation.json": master["decision"],
        "set_level_results.json": {"status": "INSUFFICIENT_EVIDENCE", "reason": "No price-independent canonical set-market outcome was joined; card-level results are primary."},
    }
    for name, value in artifacts.items(): write_json(out/name, value)
    methodology = """# Frozen Collector Appeal V7 price validation\n\nPrice is an outcome only. The frozen V7 artifact is hash-checked before and after analysis. The primary cohort is limited to sets with exact modeled pull probability. Models use leave-whole-set-out validation, set fixed effects, set-cluster inference, and whole-set bootstrap uncertainty. Scarcity is represented as `-log10(p)` because it is monotonic, finite, and interpretable as orders of rarity. Treatment is the existing diagnostic taxonomy score. No coefficient is transferred to Collector scoring. Cross-era results are exploratory only.\n"""
    (out/"methodology.md").write_text(methodology, encoding="utf-8")
    report = f"""# Collector Appeal V7 frozen price-validation report\n\n- Controlled cohort: {len(rows):,} cards across {len({r['set_id'] for r in rows})} sets.\n- Median within-set V7 rho: {within['card_appeal_v7']['summary']['medianRho']:.4f}.\n- Overall verdict: `{overall}`.\n- Promotion recommendation: `{promotion}`.\n- Production mutations: **NONE**.\n\nSee `master_result.json` for complete coefficients, uncertainty, folds, components, interactions, and sensitivity results.\n"""
    (out/"final_validation_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"rows": len(rows), "sets": len({r['set_id'] for r in rows}), "overall": overall,
                      "promotion": promotion, "output": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
