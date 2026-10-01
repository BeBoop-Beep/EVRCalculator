"""Treatment Hierarchy V4 set-local scarcity identifiability study.

Research only. Reuses the frozen expanded V3 panel and makes no provider calls
or production writes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.research_treatment_panel_recovery_v2 import (
    ROUND23_LADDERS, _build_targets, load_json, resolve_sample, stable_hash,
)
from backend.scripts.research_treatment_hierarchy_v3 import (
    _bootstrap,
    _card_context,
    _collector_controls,
    _effect_report,
    _group_decisions,
    _influence,
    _mean_centered_log_prices,
    _model,
    _pull_authority,
    _treatment_columns,
    spearman,
)

MODEL_VERSION = "treatment_hierarchy_v4_set_local_scarcity_identifiability_v1"
SIMULATION_MARKET_DATE = "2026-09-29"
EXPECTED_MANIFEST_FINGERPRINT = "55b8dcd3090acb707d101a3b03e574862cc3ef15f752c95940870f7b4b3d6e24"
EXPECTED_SAMPLE_FINGERPRINT = "7fecdbd2cb448dd9414f062d0d83b16a58b187dcbd7bf679cf781dc295d7b23e"
MIN_TEMPORAL_SPEARMAN = 0.60

DEFAULT_HISTORY = ROOT / "backend/artifacts/treatment_panel_recovery_v3_input/history.json"
DEFAULT_RECOVERY_SUMMARY = ROOT / "backend/artifacts/treatment_panel_recovery_v3_input/summary.json"
DEFAULT_MANIFEST = ROOT / "docs/research/collector_appeal/treatment_panel_recovery_v3/expanded_manifest.json"
DEFAULT_OUTPUT = ROOT / "backend/artifacts/treatment_hierarchy_v4"


def _ready_sample(recovery: Mapping[str, Any], manifest: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    full = resolve_sample(manifest, load_json(ROUND23_LADDERS))
    payload = recovery.get("panelReadiness") or {}
    rows = payload.get("identities") or [] if isinstance(payload, Mapping) else payload
    statuses = {
        str(row.get("identity")): str(row.get("status"))
        for row in rows
        if isinstance(row, Mapping)
    }
    ready = [
        row for row in full
        if statuses.get(str(row["identity"])) in {"PANEL_READY_STRONG", "PANEL_READY_MODERATE"}
    ]
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in ready:
        grouped[(str(row["era"]), str(row["set"]), str(row["family"]))].append(row)
    eligible_keys = {key for key, values in grouped.items() if len(values) >= 2}
    eligible = [
        row for row in ready
        if (str(row["era"]), str(row["set"]), str(row["family"])) in eligible_keys
    ]
    excluded = [
        {"era": key[0], "set": key[1], "family": key[2], "readyIdentities": len(values)}
        for key, values in sorted(grouped.items())
        if key not in eligible_keys
    ]
    return eligible, excluded


def _subset_context(card_ctx: Mapping[str, Mapping[str, Any]], set_name: str, family: str) -> dict[str, dict[str, Any]]:
    return {
        cid: dict(row) for cid, row in card_ctx.items()
        if str(row["set"]) == set_name and str(row["family"]) == family
    }


def _group_sample(sample: Sequence[Mapping[str, Any]], set_name: str, family: str) -> list[dict[str, Any]]:
    return [
        dict(row) for row in sample
        if str(row["set"]) == set_name and str(row["family"]) == family
    ]


def run(client: Any, *, history_path: Path, recovery_summary_path: Path, manifest_path: Path) -> dict[str, Any]:
    history = load_json(history_path)
    recovery = load_json(recovery_summary_path)
    manifest = load_json(manifest_path)
    if recovery.get("manifestFingerprint") != EXPECTED_MANIFEST_FINGERPRINT:
        raise RuntimeError("recovery manifest fingerprint drift")
    if recovery.get("sampleFingerprint") != EXPECTED_SAMPLE_FINGERPRINT:
        raise RuntimeError("recovery sample fingerprint drift")

    sample, excluded_groups = _ready_sample(recovery, manifest)
    targets, target_meta = _build_targets(client, sample)
    if target_meta["targetBuildFailures"]:
        raise RuntimeError(f"target build drift: {target_meta['targetBuildFailures']}")
    variant_ids = [str(x["selected_variant_id"]) for x in targets]
    pull = _pull_authority(client, variant_ids)
    card_ids = sorted({str(x["canonical_card_id"]) for x in targets})
    collector_version, controls = _collector_controls(client, card_ids)
    card_ctx = _card_context(sample, targets, pull, controls)

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in sample:
        grouped[(str(row["era"]), str(row["set"]), str(row["family"]))].append(dict(row))

    rank_audit = []
    local_inputs = {}
    rank_family_sets: dict[str, set[str]] = defaultdict(set)

    for (era, set_name, family), rows in sorted(grouped.items()):
        ctx = _subset_context(card_ctx, set_name, family)
        cols = _treatment_columns(ctx)
        y = _mean_centered_log_prices(rows, history, fold="full")
        package = _model(ctx, y, cols, scarcity=False)
        pure = _model(ctx, y, cols, scarcity=True)
        full_rank = bool(package.get("estimable")) and bool(pure.get("estimable"))
        if full_rank:
            rank_family_sets[family].add(set_name)
            local_inputs[(era, set_name, family)] = (rows, ctx, cols, package, pure)
        rank_audit.append({
            "era": era,
            "set": set_name,
            "family": family,
            "readyIdentities": len(rows),
            "cards": len(ctx),
            "treatmentCoefficients": len(cols),
            "packageEstimable": bool(package.get("estimable")),
            "packageRank": package.get("rank"),
            "packageColumns": package.get("columns"),
            "pureEstimable": bool(pure.get("estimable")),
            "pureRank": pure.get("rank"),
            "pureColumns": pure.get("columns"),
            "pureConditionNumber": pure.get("conditionNumber"),
            "status": "LOCAL_PURE_IDENTIFIED" if full_rank else "LOCAL_SCARCITY_UNDERIDENTIFIED",
        })

    rank_supported_families = {
        family: sorted(sets) for family, sets in rank_family_sets.items() if len(sets) >= 2
    }

    base = {
        "modelVersion": MODEL_VERSION,
        "collectorControlVersion": collector_version,
        "recoveryProvenance": {
            "workflowRunId": 36929725640,
            "artifactId": 11196076068,
            "artifactDigest": "sha256:e3dc70d260e53e079348db304774c89812b9a9fc0d35654ecf6d0470f1fc974b",
            "manifestFingerprint": recovery.get("manifestFingerprint"),
            "sampleFingerprint": recovery.get("sampleFingerprint"),
            "historyFingerprint": stable_hash(history),
            "providerCreditsUsed": recovery.get("providerCreditsUsed"),
        },
        "counts": {
            "fitCards": len(card_ctx),
            "fitIdentities": len({str(x["identity"]) for x in card_ctx.values()}),
            "fitSets": len({str(x["set"]) for x in card_ctx.values()}),
            "eligibleSetFamilies": len(grouped),
            "locallyIdentifiedSetFamilies": len(local_inputs),
        },
        "excludedGroups": excluded_groups,
        "localRankAudit": rank_audit,
        "rankSupportedFamilies": rank_supported_families,
        "databaseWrites": 0,
        "providerCalls": 0,
        "collectorMutation": False,
        "overallRipMutation": False,
    }

    if not rank_supported_families:
        return {
            **base,
            "decisionToken": "TREATMENT_HIERARCHY_V4_LOCAL_SCARCITY_UNDERIDENTIFIED",
            "stageReached": "LOCAL_IDENTIFIABILITY_GATE",
            "setFamilyResults": [],
            "globalTemporalSpearman": None,
            "passingSetFamilyCount": 0,
            "eraSupportedFamilies": {},
        }

    all_effects = {}
    group_results = []
    early_pairs: list[tuple[str, float, float]] = []

    for key, (rows, ctx, cols, package, pure) in sorted(local_inputs.items()):
        era, set_name, family = key
        y_full = _mean_centered_log_prices(rows, history, fold="full")
        y_early = _mean_centered_log_prices(rows, history, fold="early")
        y_late = _mean_centered_log_prices(rows, history, fold="late")
        early = _model(ctx, y_early, cols, scarcity=True)
        late = _model(ctx, y_late, cols, scarcity=True)
        artist = _model(ctx, y_full, cols, scarcity=True, sensitivity="artist")
        play = _model(ctx, y_full, cols, scarcity=True, sensitivity="playability")
        boot = _bootstrap(ctx, y_full, cols)
        influence = _influence(ctx, y_full, cols, pure["coefficients"])
        effects = _effect_report(cols, package, pure, early, late, boot, influence, artist, play, ctx)
        decision = _group_decisions(effects)[0]
        for col, effect in effects.items():
            all_effects[col] = effect
            if early.get("estimable") and late.get("estimable") and col in early.get("coefficients", {}) and col in late.get("coefficients", {}):
                early_pairs.append((col, float(early["coefficients"][col]), float(late["coefficients"][col])))
        group_results.append({
            "era": era, "set": set_name, "family": family,
            "readyIdentities": len(rows),
            "package": package, "pure": pure, "early": early, "late": late,
            "artistSensitivity": artist, "playabilitySensitivity": play,
            "effects": effects, "passesLocalEffectGates": bool(decision["passes"]),
        })

    rho = spearman([x[1] for x in early_pairs], [x[2] for x in early_pairs]) if len(early_pairs) >= 2 else None
    temporal_pass = rho is not None and rho >= MIN_TEMPORAL_SPEARMAN

    passing_groups = [
        row for row in group_results
        if row["passesLocalEffectGates"] and temporal_pass
    ]
    family_sets: dict[str, set[str]] = defaultdict(set)
    for row in passing_groups:
        family_sets[row["family"]].add(row["set"])
    era_supported = {
        family: sorted(sets) for family, sets in family_sets.items() if len(sets) >= 2
    }

    if era_supported:
        token = "TREATMENT_HIERARCHY_V4_SV_ERA_SUPPORTED"
    elif passing_groups:
        token = "TREATMENT_HIERARCHY_V4_SET_LOCAL_SUPPORTED"
    else:
        token = "TREATMENT_HIERARCHY_V4_DIAGNOSTIC_ONLY"

    return {
        **base,
        "decisionToken": token,
        "stageReached": "LOCAL_SUPPORT_GATES",
        "globalTemporalSpearman": rho,
        "minimumTemporalSpearman": MIN_TEMPORAL_SPEARMAN,
        "globalTemporalPass": temporal_pass,
        "effects": all_effects,
        "setFamilyResults": group_results,
        "passingSetFamilyCount": len(passing_groups),
        "eraSupportedFamilies": era_supported,
        "crossEraStatus": "NOT_REACHED_SINGLE_AUTHORIZED_ERA",
    }


def render(report: Mapping[str, Any]) -> str:
    lines = [
        "# Treatment Hierarchy V4 — Set-Local Scarcity Results",
        "",
        f"Decision: `{report['decisionToken']}`",
        "",
        "## Local identifiability",
        "",
        "| Set / family | Ready identities | Pure rank / columns | Status |",
        "|---|---:|---:|---|",
    ]
    for row in report["localRankAudit"]:
        lines.append(
            f"| {row['set']} / {row['family']} | {row['readyIdentities']} | "
            f"{row.get('pureRank')} / {row.get('pureColumns')} | {row['status']} |"
        )
    lines += [
        "",
        f"- Families with >=2 locally identified Sets: {report.get('rankSupportedFamilies')}",
        f"- Global temporal Spearman (if reached): {report.get('globalTemporalSpearman')}",
        f"- Passing Set/family groups: {report.get('passingSetFamilyCount')}",
        f"- Era-supported families: {report.get('eraSupportedFamilies')}",
        "",
        "## Boundary",
        "",
        "This is an identifiability study. Rank-deficient local PURE designs are not rescued "
        "with regularization, cross-Set scarcity coefficients, or post-hoc treatment collapsing.",
        "",
        "Production writes: 0. Provider calls: 0. Collector/Overall mutation: none.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    p.add_argument("--recovery-summary", type=Path, default=DEFAULT_RECOVERY_SUMMARY)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = p.parse_args(argv)

    load_dotenv(ROOT / "backend/.env", override=False)
    from backend.db.clients.supabase_client import create_service_role_client

    result = run(create_service_role_client(), history_path=args.history,
                 recovery_summary_path=args.recovery_summary, manifest_path=args.manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results.json").write_text(json.dumps(result, indent=2, default=str)+"\n")
    (args.output_dir / "FINAL_REPORT.md").write_text(render(result))
    (args.output_dir / "decision.json").write_text(json.dumps({
        "decisionToken": result["decisionToken"],
        "stageReached": result["stageReached"],
        "rankSupportedFamilies": result.get("rankSupportedFamilies"),
        "passingSetFamilyCount": result.get("passingSetFamilyCount"),
        "eraSupportedFamilies": result.get("eraSupportedFamilies"),
        "databaseWrites": 0,
        "providerCalls": 0,
    }, indent=2, sort_keys=True)+"\n")
    print(json.dumps({
        "decisionToken": result["decisionToken"],
        "stageReached": result["stageReached"],
        "counts": result["counts"],
        "rankSupportedFamilies": result.get("rankSupportedFamilies"),
        "globalTemporalSpearman": result.get("globalTemporalSpearman"),
        "passingSetFamilyCount": result.get("passingSetFamilyCount"),
        "eraSupportedFamilies": result.get("eraSupportedFamilies"),
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
