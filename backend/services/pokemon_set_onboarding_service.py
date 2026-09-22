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
    apply_approved_pull_model,
    generate_catalog_only_set_config,
    generate_one_set_config,
    provider_catalog_era_hint,
)
from backend.services.pokemon_tcg_api_set_service import fetch_targeted_sets, resolve_set_metadata
from backend.services.tcgplayer_set_catalog_service import build_priceguide_urls
from backend.services.pokemon_onboarding_publication_service import evaluate_onboarding_publication_readiness
from backend.services.pokemon_onboarding_simulation_service import (
    latest_simulation_evidence, parse_simulation_json,
)
from backend.services.pokemon_onboarding_verification_service import collect_final_verification

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
                "sealed_details_url,symbol_image_url,logo_image_url,ready_for_daily_scrape,"
                "catalog_only,supports_opening_simulation")
        .eq("canonical_key", canonical_key).limit(1).execute()
    )
    if not set_result.data:
        return {"public_set_correct": False}
    set_row = set_result.data[0]
    set_id = str(set_row["id"])
    cards = (
        supabase.table("cards").select("id,rarity,image_small_url,image_large_url").eq("set_id", set_id).limit(1000).execute().data or []
    )
    card_ids = [row["id"] for row in cards if row.get("id")]
    variants: list[Dict[str, Any]] = []
    for start in range(0, len(card_ids), 250):
        variants.extend(
            supabase.table("card_variants")
            .select("id,card_id,image_small_url,image_large_url")
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
    sealed_products = (
        supabase.table("sealed_products").select("id").eq("set_id", set_id).limit(1000).execute().data or []
    )
    sealed_product_ids = [row["id"] for row in sealed_products if row.get("id")]
    sealed_prices: list[Dict[str, Any]] = []
    for start in range(0, len(sealed_product_ids), 250):
        sealed_prices.extend(
            supabase.table("sealed_product_price_observations")
            .select("sealed_product_id,captured_at,market_price")
            .in_("sealed_product_id", sealed_product_ids[start:start + 250])
            .gt("market_price", 0).order("captured_at", desc=True).limit(1000).execute().data or []
        )
    latest_sealed = max(
        (str(row["captured_at"]) for row in sealed_prices if row.get("captured_at")),
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
    card_by_id = {row.get("id"): row for row in cards}
    cards_with_images = sum(1 for row in cards if row.get("image_small_url") or row.get("image_large_url"))
    images_present = sum(
        1 for row in variants
        if row.get("image_small_url") or row.get("image_large_url")
        or (card_by_id.get(row.get("card_id")) or {}).get("image_small_url")
        or (card_by_id.get(row.get("card_id")) or {}).get("image_large_url")
    )
    return {
        "set_id": set_id, "set_row": set_row, "public_set_correct": True,
        "ready_for_daily_scrape": bool(set_row.get("ready_for_daily_scrape")),
        "catalog_only": bool(set_row.get("catalog_only")),
        "supports_opening_simulation": bool(set_row.get("supports_opening_simulation")),
        "cards_populated": bool(cards), "card_count": len(cards),
        "variants_populated": bool(variants), "variant_count": len(variants),
        "market_prices_populated": bool(prices), "price_observation_count": len(prices),
        "resolved_market_date": latest[:10] if latest else None,
        "sealed_products_populated": bool(sealed_products), "sealed_product_count": len(sealed_products),
        "sealed_market_prices_populated": bool(sealed_prices),
        "sealed_price_observation_count": len(sealed_prices),
        "resolved_sealed_market_date": latest_sealed[:10] if latest_sealed else None,
        "rarity_census": rarity_counts,
        "image_coverage": (images_present / len(variants)) if variants else 0.0,
        "cards_with_images": cards_with_images, "variants_with_images": images_present,
        "eligible_card_count": len(cards), "eligible_variant_count": len(variants),
        "image_unmatched_count": max(len(variants) - images_present, 0),
        "image_ambiguous_count": None,
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
    for group in ("reverse_slot_probabilities", "rare_slot_probability", "rare_slot_probabilities"):
        values = payload.get("slot_assumptions", {}).get(group)
        if values is not None:
            groups = values.values() if values and all(isinstance(value, dict) for value in values.values()) else [values]
            for probabilities in groups:
                total = sum(float(value) for value in probabilities.values())
                if any(float(value) < 0 for value in probabilities.values()) or not math.isclose(total, 1.0, abs_tol=0.02):
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
    if payload.get("collation_compatibility_approved") is not True:
        raise ValueError("product/collation compatibility must be explicitly approved")
    if not isinstance(payload.get("pack_state_overrides"), dict):
        raise ValueError("pack_state_overrides must be an approved object")
    return payload


def validate_deployed_pull_model(config_path: Path, raw_rarities: list[str]) -> Dict[str, Any]:
    tree = ast.parse(config_path.read_text(encoding="utf-8"))
    values: Dict[str, Any] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "PULL_RATE_MAPPING", "PULL_MODEL_STATUS", "USE_MONTE_CARLO_V2",
                    "REVERSE_SLOT_PROBABILITIES", "RARE_SLOT_PROBABILITY",
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
    if not isinstance(values.get("REVERSE_SLOT_PROBABILITIES"), dict):
        raise ValueError("approved reverse slot probabilities are missing")
    if not isinstance(values.get("RARE_SLOT_PROBABILITY"), dict):
        raise ValueError("approved rare slot probability is missing")
    if not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "get_pack_state_overrides"
               for node in ast.walk(tree)):
        raise ValueError("approved pack-state override is missing")
    return {"pull_model_status": "approved", "use_monte_carlo_v2": True,
            "modeled_rarities": sorted(normalized)}


class OnboardingEngine:
    def __init__(
        self, *, execute: bool, no_git: bool = False, pull_rates_file: Optional[Path] = None,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        git_settings: Optional[GitSettings] = None,
        publication_evaluator: Callable[..., Dict[str, Any]] = evaluate_onboarding_publication_readiness,
        verification_collector: Callable[..., Dict[str, Any]] = collect_final_verification,
        simulation_evidence_collector: Callable[[Any, str], Dict[str, Any]] = latest_simulation_evidence,
        set_evidence_collector: Callable[[str], Dict[str, Any]] = collect_set_evidence,
        db_client: Any = None,
    ):
        self.execute = execute
        self.no_git = no_git
        self.pull_rates_file = pull_rates_file
        self.command_runner = command_runner
        self.git_settings = git_settings or GitSettings.from_env()
        self.publication_evaluator = publication_evaluator
        self.verification_collector = verification_collector
        self.simulation_evidence_collector = simulation_evidence_collector
        self.set_evidence_collector = set_evidence_collector
        self.db_client = db_client

    def _client(self) -> Any:
        if self.db_client is not None:
            return self.db_client
        from backend.db.clients.supabase_client import supabase
        return supabase

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
            hint = provider_catalog_era_hint(name)
            raw_confidence = metadata.get("confidence")
            if raw_confidence is None:
                raw_confidence = (metadata.get("discovery_evidence") or {}).get("confidence")
            try:
                provider_confidence = float(raw_confidence or 0.0)
            except (TypeError, ValueError):
                provider_confidence = 0.0

            def provider_only(reason: str, diagnostics: Optional[Dict[str, Any]] = None) -> Optional[StepOutcome]:
                source_id = str(job.get("source_set_id") or "").strip()
                if hint is None or provider_confidence < 0.90 or not source_id.isdigit():
                    return None
                card_url, sealed_url = build_priceguide_urls(int(source_id))
                era_folder, era_label = hint
                return _next(step, {
                    "provider_catalog_only": True,
                    "provider_metadata_reason": reason,
                    "provider_confidence": provider_confidence,
                    "provider_era_folder": era_folder,
                    "provider_era_label": era_label,
                    "source_set_id": source_id,
                    "card_details_url": card_url,
                    "sealed_details_url": sealed_url,
                    **(diagnostics or {}),
                })

            try:
                rows = fetch_targeted_sets(
                    name, os.getenv("POKEMON_TCG_API_KEY", ""),
                    timeout_seconds=float(os.getenv("POKEMON_ONBOARDING_PROVIDER_TIMEOUT_SECONDS", "15")),
                )
            except Exception as exc:
                # A missing/deprecated API credential must not make a strongly
                # validated TCGplayer expansion invisible forever. Only explicit
                # trusted provider-era prefixes are allowed through this fallback;
                # arbitrary catalog names still retry rather than being guessed.
                if "Missing POKEMON_TCG_API_KEY" in str(exc):
                    fallback = provider_only("pokemon_api_key_unavailable", {"error": str(exc)})
                    if fallback is not None:
                        return fallback
                return StepOutcome("retry", step, {"error": str(exc)}, "pokemon_api_unavailable")
            resolution = resolve_set_metadata(name, rows, expected_api_id=job.get("pokemon_api_set_id"))
            if resolution.status == "resolved":
                return _next(step, {"pokemon_api_set": resolution.set_data, **resolution.diagnostics})
            if resolution.status == "not_found":
                fallback = provider_only("pokemon_api_not_found", resolution.diagnostics)
                if fallback is not None:
                    return fallback
                return StepOutcome("wait", step, resolution.diagnostics, "pokemon_api_not_found")
            return StepOutcome(
                "manual_review", step, resolution.diagnostics, f"pokemon_api_{resolution.status}"
            )

        if step == "source_registration":
            resolved = metadata.get("steps", {}).get("metadata_resolution", {})
            api_set = resolved.get("pokemon_api_set")
            provider_catalog_only = bool(resolved.get("provider_catalog_only"))
            if not api_set and not provider_catalog_only:
                return StepOutcome("manual_review", step, {}, "missing_resolved_metadata")

            # Idempotent resume: source may already have been merged/deployed
            # while the durable onboarding job was waiting. Do not create a
            # duplicate worktree/branch/PR in that case.
            if provider_catalog_only:
                existing_canonical = __import__(
                    "backend.scripts.bootstrap_pokemon_set_configs", fromlist=["normalize_set_key"]
                ).normalize_set_key(name)
                existing_era = str(resolved.get("provider_era_folder") or "")
                existing_config = (
                    REPO_ROOT / "backend/constants/tcg/pokemon" / existing_era
                    / f"{existing_canonical}.py"
                )
                if existing_era and existing_config.exists():
                    return _next(step, {
                        "canonical_key": existing_canonical,
                        "era_folder": existing_era,
                        "provider_era_folder": existing_era,
                        "provider_catalog_only": True,
                        "source_deployed": True,
                        "config_path": str(existing_config),
                    })

            if self.no_git or self.git_settings.mode == "disabled":
                return StepOutcome(
                    "wait", step,
                    {"operator_action": "Enable POKEMON_ONBOARDING_GIT_MODE=pr and configure an isolated worktree."},
                    "source_pr_pending",
                )
            if not self.execute:
                evidence = {
                    "dry_run": True,
                    "planned_action": "prepare_worktree+commit+push_and_open_pr",
                }
                if api_set:
                    evidence["pokemon_api_set"] = api_set
                else:
                    evidence["provider_catalog_only"] = True
                    evidence["provider_era_folder"] = resolved.get("provider_era_folder")
                return StepOutcome("advance", step, evidence)

            adapter = GitAdapter(REPO_ROOT, self.git_settings, runner=self.command_runner)
            canonical_source_name = str(api_set["name"]) if api_set else name
            canonical = __import__(
                "backend.scripts.bootstrap_pokemon_set_configs", fromlist=["normalize_set_key"]
            ).normalize_set_key(canonical_source_name)
            worktree, branch = adapter.prepare_worktree(canonical)
            if api_set:
                card_url = metadata.get("card_details_url")
                sealed_url = metadata.get("sealed_details_url")
                if not card_url or not sealed_url:
                    source_id = str(job.get("source_set_id") or "")
                    if source_id.isdigit():
                        card_url, sealed_url = build_priceguide_urls(int(source_id))
                generated = generate_one_set_config(
                    worktree, api_set,
                    card_details_url=str(card_url),
                    sealed_details_url=str(sealed_url),
                )
            else:
                source_id = str(job.get("source_set_id") or "").strip()
                card_url = str(resolved["card_details_url"])
                sealed_url = str(resolved["sealed_details_url"])
                generated = generate_catalog_only_set_config(
                    worktree,
                    source_set_name=name,
                    source_set_id=source_id,
                    card_details_url=card_url,
                    sealed_details_url=sealed_url,
                    era_folder=str(resolved["provider_era_folder"]),
                )
            expected = list(generated.changed_paths)
            validation = self.command_runner(
                [sys.executable, "-m", "py_compile", str(generated.config_path)],
                cwd=str(worktree), capture_output=True, text=True, check=False,
            )
            if validation.returncode:
                return StepOutcome("manual_review", step, {"stderr": validation.stderr}, "config_validation_failed")
            sha = adapter.commit_expected_files(worktree, expected, f"Onboard Pokemon set {generated.canonical_key}")
            pr = adapter.push_and_open_pr(worktree, branch, f"Onboard Pokemon set: {name}")
            return StepOutcome(
                "wait", "awaiting_source_deploy",
                {
                    "canonical_key": generated.canonical_key, "era_folder": generated.era_folder,
                    "provider_catalog_only": provider_catalog_only,
                    "source_branch": branch, "source_commit_sha": sha, **pr,
                },
                pr["status"],
            )

        if step == "awaiting_source_deploy":
            config = REPO_ROOT / "backend/constants/tcg/pokemon" / str(job.get("era_folder")) / f"{key}.py"
            if not config.exists():
                pr_url = job.get("source_pr_url")
                if pr_url and not self.no_git and self.git_settings.mode == "pr":
                    if not self.execute:
                        return StepOutcome(
                            "wait", step,
                            {"dry_run": True, "planned_action": "reconcile_pr_and_optional_deploy",
                             "source_pr_url": pr_url},
                            "awaiting_source_deploy",
                        )
                    result = GitAdapter(REPO_ROOT, self.git_settings, runner=self.command_runner).reconcile_pr_and_optional_deploy(str(pr_url))
                    if result.get("status") != "deployed":
                        return StepOutcome("wait", step, result, str(result["status"]))
                return StepOutcome("wait", step, {"config_path": str(config)}, "awaiting_source_deploy")
            return _next(step, {"config_path": str(config), "deployed": True})

        if step == "db_registration":
            outcome = self._command(step, ["backend/scripts/sync_pokemon_eras_and_sets.py", "--set", key, "--apply"])
            if self.execute and outcome.kind == "advance":
                evidence = self.set_evidence_collector(key)
                if not evidence["public_set_correct"]:
                    return StepOutcome("retry", step, evidence, "db_registration_verification_failed")
                if not evidence["ready_for_daily_scrape"] and not evidence.get("catalog_only"):
                    return StepOutcome("retry", step, evidence, "db_registration_verification_failed")
                return _next(step, evidence)
            return outcome
        if step == "initial_scrape":
            before = self.set_evidence_collector(key) if self.execute else {}
            target_flag = "--catalog-set" if before.get("catalog_only") else "--set"
            outcome = self._command(
                step, ["backend/scripts/run_pokemon_set_scrape.py", "--run", target_flag, key]
            )
            if self.execute and outcome.kind == "advance":
                evidence = self.set_evidence_collector(key)
                if evidence.get("catalog_only"):
                    card_ok = (
                        evidence.get("cards_populated")
                        and evidence.get("variants_populated")
                        and evidence.get("market_prices_populated")
                    )
                    sealed_ok = (
                        evidence.get("sealed_products_populated")
                        and evidence.get("sealed_market_prices_populated")
                    )
                    if not (card_ok or sealed_ok):
                        return StepOutcome("retry", step, evidence, "catalog_initial_scrape_verification_failed")
                    if evidence.get("cards_populated"):
                        # A price scrape can discover cards before the metadata
                        # provider has filled image/API identity. Hydrate it in
                        # the SAME first-scrape cycle instead of waiting for an
                        # operator to notice blank cards later.
                        image_sync = self.command_runner(
                            [sys.executable, "backend/scripts/sync_pokemon_images.py", "--sets", name, "--apply"],
                            cwd=str(REPO_ROOT), capture_output=True, text=True, check=False,
                        )
                        evidence["initial_image_sync_exit_code"] = image_sync.returncode
                        evidence["initial_image_sync_stdout_tail"] = image_sync.stdout[-2000:]
                        evidence["initial_image_sync_stderr_tail"] = image_sync.stderr[-2000:]
                        if image_sync.returncode:
                            return StepOutcome("retry", step, evidence, "catalog_initial_image_sync_failed")
                        canonical = self.command_runner(
                            [
                                sys.executable,
                                "backend/scripts/build_pokemon_set_desirability_inputs.py",
                                "--set", key, "--commit", "--canonical-only",
                            ],
                            cwd=str(REPO_ROOT), capture_output=True, text=True, check=False,
                        )
                        evidence["canonical_only_exit_code"] = canonical.returncode
                        evidence["canonical_only_stdout_tail"] = canonical.stdout[-2000:]
                        evidence["canonical_only_stderr_tail"] = canonical.stderr[-2000:]
                        if canonical.returncode:
                            return StepOutcome(
                                "retry", step, evidence, "catalog_canonical_projection_failed"
                            )
                    return StepOutcome(
                        "complete", step, {**evidence, "catalog_only_onboarding_complete": True}
                    )
                required = ("cards_populated", "variants_populated", "market_prices_populated", "resolved_market_date")
                if not all(evidence.get(field) for field in required):
                    return StepOutcome("retry", step, evidence, "initial_scrape_verification_failed")

                # Initial scrape now owns first-pass card metadata hydration.
                # The later images step stays as an idempotent coverage gate,
                # but newly scraped cards should already carry provider IDs and
                # artwork before Set Value / Collector work begins.
                threshold = float(os.getenv("POKEMON_ONBOARDING_MIN_IMAGE_COVERAGE", "0.90"))
                if evidence.get("cards_populated") and float(evidence.get("image_coverage") or 0.0) < threshold:
                    image_sync = self.command_runner(
                        [sys.executable, "backend/scripts/sync_pokemon_images.py", "--sets", name, "--apply"],
                        cwd=str(REPO_ROOT), capture_output=True, text=True, check=False,
                    )
                    evidence["initial_image_sync_exit_code"] = image_sync.returncode
                    evidence["initial_image_sync_stdout_tail"] = image_sync.stdout[-2000:]
                    evidence["initial_image_sync_stderr_tail"] = image_sync.stderr[-2000:]
                    if image_sync.returncode:
                        return StepOutcome("retry", step, evidence, "initial_image_sync_failed")

                    canonical = self.command_runner(
                        [
                            sys.executable,
                            "backend/scripts/build_pokemon_set_desirability_inputs.py",
                            "--set", key, "--commit", "--canonical-only",
                        ],
                        cwd=str(REPO_ROOT), capture_output=True, text=True, check=False,
                    )
                    evidence["initial_canonical_sync_exit_code"] = canonical.returncode
                    evidence["initial_canonical_sync_stdout_tail"] = canonical.stdout[-2000:]
                    evidence["initial_canonical_sync_stderr_tail"] = canonical.stderr[-2000:]
                    if canonical.returncode:
                        return StepOutcome("retry", step, evidence, "initial_canonical_metadata_sync_failed")

                    evidence = {
                        **evidence,
                        **self.set_evidence_collector(key),
                        "image_coverage_threshold": threshold,
                        "initial_image_sync_exit_code": image_sync.returncode,
                        "initial_canonical_sync_exit_code": canonical.returncode,
                    }
                    if float(evidence.get("image_coverage") or 0.0) < threshold:
                        return StepOutcome("retry", step, evidence, "initial_image_fetch_incomplete")
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
                evidence = self.set_evidence_collector(key)
                if not evidence["positive_standard_set_value"]:
                    return StepOutcome("retry", step, evidence, "positive_standard_set_value_missing")
                return _next(step, evidence)
            return outcome
        if step == "images":
            outcome = self._command(step, ["backend/scripts/sync_pokemon_images.py", "--sets", name, "--apply"])
            if self.execute and outcome.kind == "advance":
                evidence = self.set_evidence_collector(key)
                threshold = float(os.getenv("POKEMON_ONBOARDING_MIN_IMAGE_COVERAGE", "0.90"))
                evidence["image_coverage_threshold"] = threshold
                if evidence["image_coverage"] < threshold:
                    return StepOutcome("retry", step, evidence, "image_fetch_incomplete")

                # Released market sets that intentionally do not support opening
                # simulation must not stall forever at pull-model acquisition.
                # Build every desirability layer that is valid without simulation,
                # then force the frozen Collector Appeal model to re-evaluate
                # catalog membership using the already-fresh source authority.
                if not evidence.get("catalog_only") and not evidence.get("supports_opening_simulation"):
                    desirability = self.command_runner(
                        [
                            sys.executable,
                            "backend/scripts/build_pokemon_set_desirability_inputs.py",
                            "--set", key, "--commit", "--log-level", "INFO",
                        ],
                        cwd=str(REPO_ROOT), capture_output=True, text=True, check=False,
                    )
                    evidence["static_desirability_exit_code"] = desirability.returncode
                    evidence["static_desirability_stdout_tail"] = desirability.stdout[-2000:]
                    evidence["static_desirability_stderr_tail"] = desirability.stderr[-2000:]
                    if desirability.returncode:
                        return StepOutcome("retry", step, evidence, "static_desirability_build_failed")

                    market_date = str(evidence.get("resolved_market_date") or "").strip()
                    if not market_date:
                        return StepOutcome("retry", step, evidence, "collector_refresh_market_date_missing")
                    collector = self.command_runner(
                        [
                            sys.executable,
                            "backend/scripts/operationalize_historical_rip.py",
                            "--as-of-date", market_date,
                            "--commit",
                            "--force-model-rebuild",
                        ],
                        cwd=str(REPO_ROOT), capture_output=True, text=True, check=False,
                    )
                    evidence["collector_membership_refresh_exit_code"] = collector.returncode
                    evidence["collector_membership_refresh_stdout_tail"] = collector.stdout[-2000:]
                    evidence["collector_membership_refresh_stderr_tail"] = collector.stderr[-2000:]
                    if collector.returncode:
                        return StepOutcome("retry", step, evidence, "collector_membership_refresh_failed")

                    # No pull-model/simulation stages are applicable to this set.
                    # Continue at the publication gate after static/collector
                    # enrichment succeeds rather than manufacturing simulation data.
                    return StepOutcome("advance", "publication_gate", evidence)

                return _next(step, evidence)
            return outcome
        if step == "rarity_census":
            census = metadata.get("rarity_census") or self.set_evidence_collector(key).get("rarity_census")
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
            if not self.execute:
                return StepOutcome(
                    "advance", step,
                    {"dry_run": True, "planned_action": "prepare_worktree+commit+push_and_open_pr",
                     "manifest": manifest},
                )
            adapter = GitAdapter(REPO_ROOT, self.git_settings, runner=self.command_runner)
            worktree, branch = adapter.prepare_worktree(key, phase="pull-model")
            census = metadata.get("steps", {}).get("rarity_census", {}).get("rarity_census", {})
            try:
                path = apply_approved_pull_model(
                    worktree, str(job["era_folder"]), key, manifest, census,
                )
            except Exception as exc:
                return StepOutcome("manual_review", step, {"error": str(exc)}, "rarity_census_mapping_ambiguous")
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
                if not self.execute:
                    return StepOutcome(
                        "wait", step,
                        {"dry_run": True, "planned_action": "reconcile_pr_and_optional_deploy",
                         "source_pr_url": pr_url},
                        "awaiting_pull_model_deploy",
                    )
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
            if not self.execute:
                return StepOutcome("advance", step, {"dry_run": True})
            command = [sys.executable, "backend/scripts/run_all_v2_sets.py", "--set", key, "--dry-run", "--json"]
            result = self.command_runner(command, cwd=str(REPO_ROOT), capture_output=True, text=True, check=False)
            try:
                structured = parse_simulation_json(result.stdout)
            except Exception as exc:
                return StepOutcome("retry", step, {"error": str(exc), "stdout_tail": result.stdout[-2000:]}, "simulation_preflight_invalid")
            matches = structured.get("matched_sets") or []
            valid = (
                result.returncode == 0 and structured.get("matched_set_count") == 1
                and len(matches) == 1 and matches[0].get("canonical_key") == key
                and matches[0].get("use_monte_carlo_v2") is True
                and matches[0].get("pull_model_status") == "approved"
            )
            if not valid:
                return StepOutcome("retry", step, structured, "simulation_preflight_invalid")
            return _next(step, structured)
        if step == "simulation":
            set_id = str(
                metadata.get("steps", {}).get("db_registration", {}).get("set_id")
                or self.set_evidence_collector(key).get("set_id") or ""
            )
            before = self.simulation_evidence_collector(self._client(), set_id)
            outcome = self._command(step, ["backend/scripts/run_all_v2_sets.py", "--set", key, "--json"])
            if not self.execute or outcome.kind != "advance":
                return outcome
            after = self.simulation_evidence_collector(self._client(), set_id)
            evidence = {"before": before, "after": after}
            if (
                not after.get("run_id") or after.get("run_id") == before.get("run_id")
                or str(after.get("target_id")) != set_id or not after.get("details_complete")
            ):
                return StepOutcome("retry", step, evidence, "simulation_new_run_verification_failed")
            return _next(step, evidence)
        if step == "desirability_post_sim":
            return self._command(step, [
                "backend/scripts/build_pokemon_set_desirability_inputs.py", "--set", key,
                "--commit", "--log-level", "INFO",
            ])
        if step == "publication_gate":
            evidence = self.set_evidence_collector(key)
            market_date = (
                metadata.get("steps", {}).get("initial_scrape", {}).get("resolved_market_date")
                or evidence.get("resolved_market_date")
            )
            if not market_date or not evidence.get("set_id"):
                return StepOutcome("wait", step, evidence, "set_observation_missing")
            gate = self.publication_evaluator(
                self._client(), set_id=str(evidence["set_id"]), canonical_key=key,
                market_date=str(market_date),
            )
            if not gate.get("complete") or not gate.get("dates_aligned"):
                return StepOutcome("wait", step, gate, str(gate.get("reason_code") or "publication_gate_not_ready"))
            return _next(step, gate)
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
        config_path = REPO_ROOT / "backend/constants/tcg/pokemon" / str(job.get("era_folder")) / f"{key}.py"
        verification = self.verification_collector(
            self._client(), canonical_key=key, config_path=config_path,
            min_image_coverage=float(os.getenv("POKEMON_ONBOARDING_MIN_IMAGE_COVERAGE", "0.90")),
        )
        missing = [field for field in required if not verification.get(field)]
        if missing:
            return StepOutcome("wait", step, {"missing": missing}, "final_verification_incomplete")
        return StepOutcome("complete", step, {"final_verification": verification})
