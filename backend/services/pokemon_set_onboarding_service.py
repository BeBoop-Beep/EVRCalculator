from __future__ import annotations

import json
import ast
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.services.pokemon_onboarding_git_service import GitAdapter, GitSettings
from backend.services.pokemon_set_config_generation_service import (
    apply_approved_pull_model, generate_one_set_config,
)
from backend.services.pokemon_tcg_api_set_service import fetch_targeted_sets, resolve_set_metadata

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class StepOutcome:
    kind: str  # advance | wait | retry | manual_review | complete
    step: str
    evidence: Dict[str, Any]
    error_code: Optional[str] = None


STEP_ORDER = (
    "metadata_resolution",
    "source_registration",
    "awaiting_source_deploy",
    "db_registration",
    "initial_scrape",
    "set_value",
    "images",
    "rarity_census",
    "pull_model_source",
    "awaiting_pull_model_deploy",
    "pull_model_validation",
    "desirability_pre_sim",
    "simulation_preflight",
    "simulation",
    "desirability_post_sim",
    "publication_gate",
    "market_snapshots",
    "explore_rankings",
    "set_page_snapshot",
    "final_verification",
)


def collect_set_evidence(canonical_key: str) -> Dict[str, Any]:
    """Collect bounded set-local evidence; callers decide which fields gate a step."""
    from backend.db.clients.supabase_client import supabase
    set_result = (
        supabase.table("sets")
        .select("id,canonical_key,name,pokemon_api_set_id,release_date,card_details_url,"
                "sealed_details_url,symbol_image_url,logo_image_url,ready_for_daily_scrape")
        .eq("canonical_key", canonical_key).limit(1).execute()
    )
    if not set_result.data:
        return {"public_set_correct": False}
    set_row = set_result.data[0]
    set_id = str(set_row["id"])
    cards = (
        supabase.table("cards").select("id,rarity").eq("set_id", set_id).limit(1000).execute().data or []
    )
    card_ids = [row["id"] for row in cards if row.get("id")]
    variants: list[Dict[str, Any]] = []
    for start in range(0, len(card_ids), 250):
        variants.extend(
            supabase.table("card_variants")
            .select("id,image_url,image_url_small,image_url_large")
            .in_("card_id", card_ids[start:start + 250]).execute().data or []
        )
    variant_ids = [row["id"] for row in variants if row.get("id")]
    prices: list[Dict[str, Any]] = []
    for start in range(0, len(variant_ids), 250):
        prices.extend(
            supabase.table("card_variant_price_observations")
            .select("card_variant_id,captured_at,market_price")
            .in_("card_variant_id", variant_ids[start:start + 250])
            .gt("market_price", 0).order("captured_at", desc=True).limit(1000).execute().data or []
        )
    latest = max(
        (str(row["captured_at"]) for row in prices if row.get("captured_at")),
        default=None,
    )
    rarity_counts: Dict[str, int] = {}
    for row in cards:
        rarity = " ".join(str(row.get("rarity") or "").strip().lower().split())
        if rarity:
            rarity_counts[rarity] = rarity_counts.get(rarity, 0) + 1
    set_values = (
        supabase.table("pokemon_set_value_daily_history")
        .select("snapshot_date,set_value,value_scope")
        .eq("set_id", set_id).eq("value_scope", "standard")
        .gt("set_value", 0).order("snapshot_date", desc=True).limit(1).execute().data or []
    )
    images_present = sum(
        1 for row in variants if row.get("image_url") or row.get("image_url_small") or row.get("image_url_large")
    )
    return {
        "set_id": set_id, "set_row": set_row, "public_set_correct": True,
        "ready_for_daily_scrape": bool(set_row.get("ready_for_daily_scrape")),
        "cards_populated": bool(cards), "card_count": len(cards),
        "variants_populated": bool(variants), "variant_count": len(variants),
        "market_prices_populated": bool(prices), "price_observation_count": len(prices),
        "resolved_market_date": latest[:10] if latest else None,
        "rarity_census": rarity_counts,
        "image_coverage": (images_present / len(variants)) if variants else 0.0,
        "positive_standard_set_value": bool(set_values),
        "set_value_row": set_values[0] if set_values else None,
    }


def _next(step: str, evidence: Dict[str, Any]) -> StepOutcome:
    index = STEP_ORDER.index(step)
    return StepOutcome("advance", STEP_ORDER[index + 1], evidence)


def validate_pull_rates_manifest(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = ("provenance", "captured_date", "rarity_denominators", "slot_assumptions", "product_type")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise ValueError(f"pull-rate manifest missing fields: {missing}")
    provenance = payload["provenance"]
    if not isinstance(provenance, dict) or not (provenance.get("source_urls") or provenance.get("citations")):
        raise ValueError("pull-rate manifest requires source_urls or citations")
    date.fromisoformat(str(payload["captured_date"]))
    denominators = payload["rarity_denominators"]
    if not isinstance(denominators, dict) or not denominators:
        raise ValueError("rarity_denominators must be a non-empty object")
    for rarity, value in denominators.items():
        number = float(value)
        if not rarity or not math.isfinite(number) or number <= 0:
            raise ValueError(f"invalid rarity denominator: {rarity!r}={value!r}")
    for group in ("reverse_slot_probabilities", "rare_slot_probabilities"):
        values = payload.get("slot_assumptions", {}).get(group)
        if values is not None:
            total = sum(float(value) for value in values.values())
            if any(float(value) < 0 for value in values.values()) or not math.isclose(total, 1.0, abs_tol=0.02):
                raise ValueError(f"{group} must be nonnegative and sum approximately to 1")
    if payload.get("slot_assumptions", {}).get("negative_residual"):
        raise ValueError("pull-rate manifest contains a negative residual")
    checks = payload.get("validation") or {}
    required_checks = (
        "no_pack_odds_scaling_error", "valid_pack_state_override",
        "supported_product_collation", "all_required_rarities_classified",
    )
    if not all(checks.get(name) is True for name in required_checks):
        raise ValueError(f"pull-rate manifest validation checks must all pass: {required_checks}")
    return payload


def validate_deployed_pull_model(config_path: Path, raw_rarities: list[str]) -> Dict[str, Any]:
    tree = ast.parse(config_path.read_text(encoding="utf-8"))
    values: Dict[str, Any] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "PULL_RATE_MAPPING", "PULL_MODEL_STATUS", "USE_MONTE_CARLO_V2",
                }:
                    values[target.id] = ast.literal_eval(node.value)
    mapping = values.get("PULL_RATE_MAPPING") or {}
    if values.get("PULL_MODEL_STATUS") != "approved" or values.get("USE_MONTE_CARLO_V2") is not True:
        raise ValueError("pull model is not approved and V2-enabled")
    if not isinstance(mapping, dict) or any(
        not str(key).strip() or not math.isfinite(float(value)) or float(value) <= 0
        for key, value in mapping.items()
    ):
        raise ValueError("pull model contains blank, non-finite, or nonpositive denominators")
    normalized = {" ".join(str(key).strip().lower().split()) for key in mapping}
    unclassified = sorted(set(raw_rarities) - normalized)
    if unclassified:
        raise ValueError(f"raw rarities are unclassified: {unclassified}")
    return {"pull_model_status": "approved", "use_monte_carlo_v2": True,
            "modeled_rarities": sorted(normalized)}


class OnboardingEngine:
    def __init__(
        self, *, execute: bool, no_git: bool = False, pull_rates_file: Optional[Path] = None,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        git_settings: Optional[GitSettings] = None,
    ):
        self.execute = execute
        self.no_git = no_git
        self.pull_rates_file = pull_rates_file
        self.command_runner = command_runner
        self.git_settings = git_settings or GitSettings.from_env()

    def _command(self, step: str, args: list[str], evidence: Optional[Dict[str, Any]] = None) -> StepOutcome:
        command = [sys.executable, *args]
        if not self.execute:
            return StepOutcome("advance", step, {"command": command, "dry_run": True})
        result = self.command_runner(command, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)
        details = {
            **(evidence or {}), "command": command, "exit_code": result.returncode,
            "stdout_tail": result.stdout[-2000:], "stderr_tail": result.stderr[-2000:],
        }
        if result.returncode:
            return StepOutcome("retry", step, details, f"{step}_command_failed")
        return _next(step, details)

    def run_step(self, job: Dict[str, Any]) -> StepOutcome:
        step = str(job.get("current_step") or "metadata_resolution")
        if step not in STEP_ORDER:
            return StepOutcome("manual_review", step, {}, "unknown_step")
        metadata = dict(job.get("metadata_json") or {})
        key = str(job.get("canonical_key") or "")
        name = str(job["source_set_name"])

        if step == "metadata_resolution":
            try:
                rows = fetch_targeted_sets(
                    name, os.getenv("POKEMON_TCG_API_KEY", ""),
                    timeout_seconds=float(os.getenv("POKEMON_ONBOARDING_PROVIDER_TIMEOUT_SECONDS", "15")),
                )
            except Exception as exc:
                return StepOutcome("retry", step, {"error": str(exc)}, "pokemon_api_unavailable")
            resolution = resolve_set_metadata(name, rows, expected_api_id=job.get("pokemon_api_set_id"))
            if resolution.status != "resolved":
                kind = "manual_review" if resolution.status in {"ambiguous", "identity_conflict"} else "wait"
                return StepOutcome(kind, step, resolution.diagnostics, f"pokemon_api_{resolution.status}")
            return _next(step, {"pokemon_api_set": resolution.set_data, **resolution.diagnostics})

        if step == "source_registration":
            api_set = metadata.get("steps", {}).get("metadata_resolution", {}).get("pokemon_api_set")
            if not api_set:
                return StepOutcome("manual_review", step, {}, "missing_resolved_metadata")
            if self.no_git or self.git_settings.mode == "disabled":
                return StepOutcome(
                    "wait", step,
                    {"operator_action": "Enable POKEMON_ONBOARDING_GIT_MODE=pr and configure an isolated worktree."},
                    "source_pr_pending",
                )
            adapter = GitAdapter(REPO_ROOT, self.git_settings, runner=self.command_runner)
            canonical = __import__(
                "backend.scripts.bootstrap_pokemon_set_configs", fromlist=["normalize_set_key"]
            ).normalize_set_key(api_set["name"])
            worktree, branch = adapter.prepare_worktree(canonical)
            generated = generate_one_set_config(
                worktree, api_set,
                card_details_url=metadata["card_details_url"],
                sealed_details_url=metadata["sealed_details_url"],
            )
            expected = list(generated.changed_paths)
            validation = self.command_runner(
                [sys.executable, "-m", "py_compile", str(generated.config_path)],
                cwd=str(worktree), capture_output=True, text=True, check=False,
            )
            if validation.returncode:
                return StepOutcome("manual_review", step, {"stderr": validation.stderr}, "config_validation_failed")
            sha = adapter.commit_expected_files(worktree, expected, f"Onboard Pokemon set {generated.canonical_key}")
            pr = adapter.push_and_open_pr(worktree, branch, f"Onboard Pokemon set: {api_set['name']}")
            return StepOutcome(
                "wait", "awaiting_source_deploy",
                {
                    "canonical_key": generated.canonical_key, "era_folder": generated.era_folder,
                    "source_branch": branch, "source_commit_sha": sha, **pr,
                },
                pr["status"],
            )

        if step == "awaiting_source_deploy":
            config = REPO_ROOT / "backend/constants/tcg/pokemon" / str(job.get("era_folder")) / f"{key}.py"
            if not config.exists():
                pr_url = job.get("source_pr_url")
                if pr_url and not self.no_git and self.git_settings.mode == "pr":
                    result = GitAdapter(REPO_ROOT, self.git_settings, runner=self.command_runner).reconcile_pr_and_optional_deploy(str(pr_url))
                    if result.get("status") != "deployed":
                        return StepOutcome("wait", step, result, str(result["status"]))
                return StepOutcome("wait", step, {"config_path": str(config)}, "awaiting_source_deploy")
            return _next(step, {"config_path": str(config), "deployed": True})

        if step == "db_registration":
            outcome = self._command(step, ["backend/scripts/sync_pokemon_eras_and_sets.py", "--set", key, "--apply"])
            if self.execute and outcome.kind == "advance":
                evidence = collect_set_evidence(key)
                if not evidence["public_set_correct"] or not evidence["ready_for_daily_scrape"]:
                    return StepOutcome("retry", step, evidence, "db_registration_verification_failed")
                return _next(step, evidence)
            return outcome
        if step == "initial_scrape":
            outcome = self._command(step, ["backend/scripts/run_pokemon_set_scrape.py", "--run", "--set", key])
            if self.execute and outcome.kind == "advance":
                evidence = collect_set_evidence(key)
                required = ("cards_populated", "variants_populated", "market_prices_populated", "resolved_market_date")
                if not all(evidence.get(field) for field in required):
                    return StepOutcome("retry", step, evidence, "initial_scrape_verification_failed")
                return _next(step, evidence)
            return outcome
        if step == "set_value":
            market_date = metadata.get("resolved_market_date") or (
                metadata.get("steps", {}).get("initial_scrape", {}).get("resolved_market_date")
            )
            if not market_date:
                return StepOutcome("retry", step, {}, "market_observation_date_unavailable")
            outcome = self._command(step, [
                "backend/scripts/backfill_pokemon_set_value_daily_history.py", "--set", key,
                "--start-date", market_date, "--end-date", market_date, "--commit",
            ])
            if self.execute and outcome.kind == "advance":
                evidence = collect_set_evidence(key)
                if not evidence["positive_standard_set_value"]:
                    return StepOutcome("retry", step, evidence, "positive_standard_set_value_missing")
                return _next(step, evidence)
            return outcome
        if step == "images":
            outcome = self._command(step, ["backend/scripts/sync_pokemon_images.py", "--sets", name, "--apply"])
            if self.execute and outcome.kind == "advance":
                evidence = collect_set_evidence(key)
                if evidence["image_coverage"] <= 0:
                    return StepOutcome("retry", step, evidence, "image_fetch_incomplete")
                return _next(step, evidence)
            return outcome
        if step == "rarity_census":
            census = metadata.get("rarity_census") or collect_set_evidence(key).get("rarity_census")
            if not census:
                return StepOutcome("retry", step, {}, "rarity_census_unavailable")
            return _next(step, {"rarity_census": census})
        if step == "pull_model_source":
            if not self.pull_rates_file:
                return StepOutcome("wait", step, {}, "awaiting_pull_rates")
            try:
                manifest = validate_pull_rates_manifest(self.pull_rates_file)
            except Exception as exc:
                return StepOutcome("manual_review", step, {"error": str(exc)}, "invalid_pull_rates_manifest")
            if self.no_git or self.git_settings.mode == "disabled":
                return StepOutcome(
                    "wait", step,
                    {"manifest": manifest,
                     "operator_action": "Enable Git PR mode to create the isolated pull-model source PR."},
                    "pull_model_source_pending",
                )
            adapter = GitAdapter(REPO_ROOT, self.git_settings, runner=self.command_runner)
            worktree, branch = adapter.prepare_worktree(key, phase="pull-model")
            path = apply_approved_pull_model(worktree, str(job["era_folder"]), key, manifest)
            validation = self.command_runner(
                [sys.executable, "-m", "py_compile", str(path)],
                cwd=str(worktree), capture_output=True, text=True, check=False,
            )
            if validation.returncode:
                return StepOutcome("manual_review", step, {"stderr": validation.stderr}, "pull_model_validation_failed")
            sha = adapter.commit_expected_files(worktree, [path], f"Approve Pokemon pull model {key}")
            pr = adapter.push_and_open_pr(worktree, branch, f"Approve Pokemon pull model: {name}")
            return StepOutcome(
                "wait", "awaiting_pull_model_deploy",
                {"manifest": manifest, "source_branch": branch, "source_commit_sha": sha, **pr},
                pr["status"],
            )
        if step == "awaiting_pull_model_deploy":
            config = REPO_ROOT / "backend/constants/tcg/pokemon" / str(job.get("era_folder")) / f"{key}.py"
            census = metadata.get("steps", {}).get("rarity_census", {}).get("rarity_census", {})
            pr_url = job.get("source_pr_url")
            if pr_url and not self.no_git and self.git_settings.mode == "pr":
                result = GitAdapter(REPO_ROOT, self.git_settings, runner=self.command_runner).reconcile_pr_and_optional_deploy(str(pr_url))
                if result.get("status") != "deployed" and self.git_settings.auto_deploy:
                    return StepOutcome("wait", step, result, str(result["status"]))
            if not config.exists():
                return StepOutcome("wait", step, {"config_path": str(config)}, "awaiting_pull_model_deploy")
            try:
                validation = validate_deployed_pull_model(config, list(census))
            except Exception as exc:
                return StepOutcome("wait", step, {"error": str(exc)}, "awaiting_pull_model_deploy")
            return _next(step, validation)
        if step == "pull_model_validation":
            deployed = metadata.get("steps", {}).get("awaiting_pull_model_deploy", {})
            if deployed.get("pull_model_status") != "approved":
                return StepOutcome("wait", step, {}, "awaiting_approved_pull_model")
            return _next(step, {"pull_model_status": "approved", "use_monte_carlo_v2": True})
        if step == "desirability_pre_sim":
            return self._command(step, [
                "backend/scripts/build_pokemon_set_desirability_inputs.py", "--set", key,
                "--commit", "--log-level", "INFO",
            ])
        if step == "simulation_preflight":
            return self._command(step, ["backend/scripts/run_all_v2_sets.py", "--set", key, "--dry-run"])
        if step == "simulation":
            return self._command(step, ["backend/scripts/run_all_v2_sets.py", "--set", key])
        if step == "desirability_post_sim":
            return self._command(step, [
                "backend/scripts/build_pokemon_set_desirability_inputs.py", "--set", key,
                "--commit", "--log-level", "INFO",
            ])
        if step == "publication_gate":
            gate = metadata.get("publication_gate")
            if not gate or not gate.get("complete") or not gate.get("dates_aligned"):
                return StepOutcome("wait", step, {"publication_gate": gate}, "publication_gate_not_ready")
            return _next(step, {"publication_gate": gate})
        if step == "market_snapshots":
            return self._command(step, [
                "backend/scripts/build_pokemon_set_market_snapshots.py", "--set-id", key,
                "--commit", "--days", "365", "--window", "365d",
            ])
        if step == "explore_rankings":
            return self._command(step, [
                "backend/scripts/build_pokemon_explore_rankings_snapshot.py", "--all", "--commit",
            ])
        if step == "set_page_snapshot":
            return self._command(step, [
                "backend/scripts/build_pokemon_set_page_snapshots.py", "--set-id", key, "--commit",
            ])
        required = (
            "source_config_registered", "public_set_correct", "ready_for_daily_scrape",
            "cards_populated", "variants_populated", "market_prices_populated",
            "image_coverage_acceptable", "positive_standard_set_value", "approved_pull_model",
            "current_simulation", "simulation_details", "current_desirability_components",
            "canonical_ca7", "overall_rip", "current_opvc", "current_top_chase",
            "explore_contains_set", "set_page_snapshot", "source_dates_align",
            "no_mixed_generation_warning", "no_satisfiable_missing_input_warning",
        )
        verification = metadata.get("final_verification") or {}
        missing = [field for field in required if not verification.get(field)]
        if missing:
            return StepOutcome("wait", step, {"missing": missing}, "final_verification_incomplete")
        return StepOutcome("complete", step, {"final_verification": verification})
