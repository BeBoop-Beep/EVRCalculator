import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from backend.services import pokemon_set_onboarding_service as service
from backend.services.pokemon_onboarding_git_service import GitSettings
from backend.services.pokemon_set_onboarding_service import (
    OnboardingEngine, STEP_ORDER, validate_pull_rates_manifest,
)


def _job(step, metadata=None):
    return {
        "id": "job", "current_step": step, "canonical_key": "futureSet",
        "source_set_name": "Future Set", "metadata_json": metadata or {},
    }


def test_step_order_places_pre_and_post_desirability_around_simulation():
    assert STEP_ORDER.index("desirability_pre_sim") < STEP_ORDER.index("simulation")
    assert STEP_ORDER.index("simulation") < STEP_ORDER.index("desirability_post_sim")
    assert STEP_ORDER.index("explore_rankings") < STEP_ORDER.index("set_page_snapshot")


def test_pending_pull_model_blocks_simulation():
    outcome = OnboardingEngine(execute=True).run_step(_job("pull_model_validation"))
    assert outcome.kind == "wait"
    assert outcome.error_code == "awaiting_approved_pull_model"


def test_publication_gate_never_adds_force_publish():
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, stdout="", stderr="")
    job = _job("market_snapshots")
    outcome = OnboardingEngine(execute=True, command_runner=runner).run_step(job)
    assert outcome.kind == "advance"
    assert "--force-publish" not in calls[0]
    assert calls[0][-4:] == ["--days", "365", "--window", "365d"]


def test_pull_manifest_requires_provenance_and_positive_denominators(tmp_path: Path):
    path = tmp_path / "rates.json"
    path.write_text(json.dumps({
        "provenance": {"source_urls": ["https://source"]}, "captured_date": "2026-08-01",
        "rarity_denominators": {"rare": 10}, "slot_assumptions": {
            "rare_slot_probabilities": {"rare": 1.0},
        }, "product_type": "standard_booster",
        "collation_compatibility_approved": True,
        "pack_state_overrides": {},
        "validation": {
            "no_pack_odds_scaling_error": True, "valid_pack_state_override": True,
            "supported_product_collation": True, "all_required_rarities_classified": True,
        },
    }), encoding="utf-8")
    assert validate_pull_rates_manifest(path)["rarity_denominators"]["rare"] == 10
    payload = json.loads(path.read_text())
    payload["rarity_denominators"]["rare"] = 0
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid rarity denominator"):
        validate_pull_rates_manifest(path)


@pytest.mark.parametrize("count", [0, 2])
def test_simulation_preflight_requires_exactly_one_match(count):
    payload = {
        "matched_set_count": count,
        "matched_sets": [
            {"canonical_key": "futureSet", "use_monte_carlo_v2": True, "pull_model_status": "approved"}
            for _ in range(count)
        ],
    }
    runner = lambda command, **kwargs: CompletedProcess(
        command, 0, stdout="SIMULATION_JSON=" + json.dumps(payload), stderr="",
    )
    outcome = OnboardingEngine(execute=True, command_runner=runner).run_step(_job("simulation_preflight"))
    assert outcome.kind == "retry"


def test_simulation_preflight_accepts_one_expected_approved_set():
    payload = {"matched_set_count": 1, "matched_sets": [
        {"canonical_key": "futureSet", "use_monte_carlo_v2": True, "pull_model_status": "approved"},
    ]}
    runner = lambda command, **kwargs: CompletedProcess(
        command, 0, stdout="SIMULATION_JSON=" + json.dumps(payload), stderr="",
    )
    assert OnboardingEngine(execute=True, command_runner=runner).run_step(
        _job("simulation_preflight")
    ).kind == "advance"


def test_simulation_requires_new_run_and_details():
    snapshots = iter([
        {"run_id": "old", "target_id": "set", "details_complete": True},
        {"run_id": "new", "target_id": "set", "details_complete": True},
    ])
    engine = OnboardingEngine(
        execute=True,
        command_runner=lambda command, **kwargs: CompletedProcess(command, 0, stdout="", stderr=""),
        set_evidence_collector=lambda key: {"set_id": "set"},
        simulation_evidence_collector=lambda client, set_id: next(snapshots),
        db_client=object(),
    )
    assert engine.run_step(_job("simulation")).kind == "advance"


def _pr_git_settings(tmp_path: Path) -> GitSettings:
    return GitSettings(mode="pr", worktree_dir=tmp_path / "worktrees", base_branch="main")


def _forbidden_runner(command, **kwargs):
    raise AssertionError(f"dry-run must not execute git/gh commands, got: {command}")


def test_dry_run_source_registration_never_touches_git():
    job = _job("source_registration", {
        "steps": {"metadata_resolution": {"pokemon_api_set": {"id": "1", "name": "Future Set"}}},
    })
    engine = OnboardingEngine(
        execute=False, command_runner=_forbidden_runner,
        git_settings=GitSettings(mode="pr", worktree_dir=Path("/tmp/onboarding-worktrees")),
    )
    outcome = engine.run_step(job)
    assert outcome.evidence.get("dry_run") is True
    assert outcome.error_code is None


def test_dry_run_awaiting_source_deploy_never_touches_git(tmp_path: Path):
    job = _job("awaiting_source_deploy", {})
    job["era_folder"] = "otherEra"
    job["source_pr_url"] = "https://github.com/example/repo/pull/1"
    engine = OnboardingEngine(
        execute=False, command_runner=_forbidden_runner, git_settings=_pr_git_settings(tmp_path),
    )
    outcome = engine.run_step(job)
    assert outcome.kind == "wait"
    assert outcome.evidence.get("dry_run") is True


def test_dry_run_pull_model_source_never_touches_git(tmp_path: Path):
    rates_path = tmp_path / "rates.json"
    rates_path.write_text(json.dumps({
        "provenance": {"source_urls": ["https://source"]}, "captured_date": "2026-08-01",
        "rarity_denominators": {"rare": 10}, "slot_assumptions": {
            "rare_slot_probabilities": {"rare": 1.0},
        }, "product_type": "standard_booster",
        "collation_compatibility_approved": True,
        "pack_state_overrides": {},
        "validation": {
            "no_pack_odds_scaling_error": True, "valid_pack_state_override": True,
            "supported_product_collation": True, "all_required_rarities_classified": True,
        },
    }), encoding="utf-8")
    job = _job("pull_model_source", {"steps": {"rarity_census": {"rarity_census": {"rare": 1}}}})
    job["era_folder"] = "otherEra"
    engine = OnboardingEngine(
        execute=False, command_runner=_forbidden_runner, pull_rates_file=rates_path,
        git_settings=_pr_git_settings(tmp_path),
    )
    outcome = engine.run_step(job)
    assert outcome.evidence.get("dry_run") is True
    assert outcome.error_code is None


def test_dry_run_awaiting_pull_model_deploy_never_touches_git(tmp_path: Path):
    job = _job("awaiting_pull_model_deploy", {"steps": {"rarity_census": {"rarity_census": {"rare": 1}}}})
    job["era_folder"] = "otherEra"
    job["source_pr_url"] = "https://github.com/example/repo/pull/2"
    engine = OnboardingEngine(
        execute=False, command_runner=_forbidden_runner, git_settings=_pr_git_settings(tmp_path),
    )
    outcome = engine.run_step(job)
    assert outcome.kind == "wait"
    assert outcome.evidence.get("dry_run") is True


def test_stale_simulation_run_is_insufficient():
    engine = OnboardingEngine(
        execute=True,
        command_runner=lambda command, **kwargs: CompletedProcess(command, 0, stdout="", stderr=""),
        set_evidence_collector=lambda key: {"set_id": "set"},
        simulation_evidence_collector=lambda client, set_id: {
            "run_id": "old", "target_id": "set", "details_complete": True,
        },
        db_client=object(),
    )
    assert engine.run_step(_job("simulation")).error_code == "simulation_new_run_verification_failed"


def _provider_job(step="metadata_resolution", metadata=None):
    job = _job(step, metadata)
    job["source_set_name"] = "ME06: Delta Reign"
    job["source_set_id"] = "24831"
    job["pokemon_api_set_id"] = None
    return job


def test_metadata_resolution_missing_api_key_falls_back_for_trusted_provider_identity(monkeypatch):
    monkeypatch.setattr(
        service,
        "fetch_targeted_sets",
        lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("Missing POKEMON_TCG_API_KEY environment variable")
        ),
    )
    outcome = OnboardingEngine(execute=True).run_step(
        _provider_job(metadata={"confidence": 0.92})
    )
    assert outcome.kind == "advance"
    assert outcome.step == "source_registration"
    assert outcome.evidence["provider_catalog_only"] is True
    assert outcome.evidence["provider_era_folder"] == "megaEvolutionEra"
    assert outcome.evidence["source_set_id"] == "24831"
    assert "/24831/" in outcome.evidence["sealed_details_url"]


def test_metadata_resolution_missing_api_key_does_not_guess_unknown_provider_era(monkeypatch):
    monkeypatch.setattr(
        service,
        "fetch_targeted_sets",
        lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("Missing POKEMON_TCG_API_KEY environment variable")
        ),
    )
    job = _job("metadata_resolution", {"confidence": 0.99})
    job["source_set_name"] = "Mystery Collection 2027"
    job["source_set_id"] = "99999"
    outcome = OnboardingEngine(execute=True).run_step(job)
    assert outcome.kind == "retry"
    assert outcome.error_code == "pokemon_api_unavailable"


def test_dry_run_provider_only_source_registration_never_touches_git():
    job = _provider_job(
        "source_registration",
        {
            "steps": {
                "metadata_resolution": {
                    "provider_catalog_only": True,
                    "provider_era_folder": "megaEvolutionEra",
                    "card_details_url": "https://tcg/cards",
                    "sealed_details_url": "https://tcg/sealed",
                }
            }
        },
    )
    engine = OnboardingEngine(
        execute=False,
        command_runner=_forbidden_runner,
        git_settings=GitSettings(mode="pr", worktree_dir=Path("/tmp/onboarding-worktrees")),
    )
    outcome = engine.run_step(job)
    assert outcome.kind == "advance"
    assert outcome.evidence["provider_catalog_only"] is True
    assert outcome.evidence["provider_era_folder"] == "megaEvolutionEra"


def test_db_registration_accepts_catalog_only_set_without_daily_scrape_readiness():
    runner = lambda command, **kwargs: CompletedProcess(command, 0, stdout="", stderr="")
    engine = OnboardingEngine(
        execute=True,
        command_runner=runner,
        set_evidence_collector=lambda _key: {
            "public_set_correct": True,
            "ready_for_daily_scrape": False,
            "catalog_only": True,
        },
    )
    outcome = engine.run_step(_provider_job("db_registration"))
    assert outcome.kind == "advance"
    assert outcome.step == "initial_scrape"


def test_initial_scrape_uses_catalog_target_and_completes_for_sealed_only_set():
    calls = []
    def runner(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, stdout="", stderr="")

    evidence = {
        "public_set_correct": True,
        "catalog_only": True,
        "ready_for_daily_scrape": False,
        "cards_populated": False,
        "variants_populated": False,
        "market_prices_populated": False,
        "sealed_products_populated": True,
        "sealed_market_prices_populated": True,
    }
    engine = OnboardingEngine(
        execute=True,
        command_runner=runner,
        set_evidence_collector=lambda _key: dict(evidence),
    )
    outcome = engine.run_step(_provider_job("initial_scrape"))
    assert outcome.kind == "complete"
    assert outcome.evidence["catalog_only_onboarding_complete"] is True
    assert "--catalog-set" in calls[0]
    assert "--set" not in calls[0]


def test_provider_source_registration_resumes_when_config_already_deployed(monkeypatch, tmp_path):
    era_dir = tmp_path / "backend/constants/tcg/pokemon/megaEvolutionEra"
    era_dir.mkdir(parents=True)
    config = era_dir / "me06DeltaReign.py"
    config.write_text("class Existing: pass\n", encoding="utf-8")
    monkeypatch.setattr(service, "REPO_ROOT", tmp_path)

    job = _provider_job(
        "source_registration",
        {
            "steps": {
                "metadata_resolution": {
                    "provider_catalog_only": True,
                    "provider_era_folder": "megaEvolutionEra",
                    "card_details_url": "https://tcg/cards",
                    "sealed_details_url": "https://tcg/sealed",
                }
            }
        },
    )
    engine = OnboardingEngine(
        execute=True,
        command_runner=_forbidden_runner,
        git_settings=GitSettings(mode="pr", worktree_dir=tmp_path / "worktrees"),
    )
    outcome = engine.run_step(job)
    assert outcome.kind == "advance"
    assert outcome.step == "awaiting_source_deploy"
    assert outcome.evidence["canonical_key"] == "me06DeltaReign"
    assert outcome.evidence["era_folder"] == "megaEvolutionEra"
    assert outcome.evidence["source_deployed"] is True



def test_initial_scrape_hydrates_missing_card_metadata_before_advancing():
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    low = {
        "catalog_only": False,
        "cards_populated": True,
        "variants_populated": True,
        "market_prices_populated": True,
        "resolved_market_date": "2026-09-21",
        "image_coverage": 0.0,
    }
    high = {**low, "image_coverage": 1.0}
    evidence = iter([
        {"catalog_only": False},  # pre-scrape routing decision
        low,                       # first post-scrape verification
        high,                      # after metadata hydration
    ])
    engine = OnboardingEngine(
        execute=True,
        command_runner=runner,
        set_evidence_collector=lambda _key: dict(next(evidence)),
    )

    outcome = engine.run_step(_job("initial_scrape"))

    assert outcome.kind == "advance"
    assert outcome.step == "set_value"
    joined = [" ".join(map(str, command)) for command in calls]
    assert any("run_pokemon_set_scrape.py --run --set futureSet" in command for command in joined)
    assert any("sync_pokemon_images.py --sets Future Set --apply" in command for command in joined)
    assert any(
        "build_pokemon_set_desirability_inputs.py --set futureSet --commit --canonical-only" in command
        for command in joined
    )
    assert outcome.evidence["image_coverage"] == 1.0


def test_images_step_builds_static_and_collector_layers_for_released_non_simulation_set():
    calls = []

    def runner(command, **kwargs):
        calls.append([str(part) for part in command])
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    engine = OnboardingEngine(
        execute=True,
        command_runner=runner,
        set_evidence_collector=lambda _key: {
            "catalog_only": False,
            "supports_opening_simulation": False,
            "image_coverage": 1.0,
            "resolved_market_date": "2026-09-22",
        },
    )
    outcome = engine.run_step(_job("images"))

    assert outcome.kind == "advance"
    assert outcome.step == "publication_gate"
    joined = [" ".join(command) for command in calls]
    assert any("sync_pokemon_images.py --sets Future Set --apply" in line for line in joined)
    assert any(
        "build_pokemon_set_desirability_inputs.py --set futureSet --commit --log-level INFO" in line
        for line in joined
    )
    assert any(
        "operationalize_historical_rip.py --as-of-date 2026-09-22 --commit --force-model-rebuild --reuse-current-source-authority" in line
        for line in joined
    )


def test_images_step_non_simulation_collector_failure_retries():
    calls = []

    def runner(command, **kwargs):
        calls.append([str(part) for part in command])
        failed = any(str(part).endswith("operationalize_historical_rip.py") for part in command)
        return CompletedProcess(command, 2 if failed else 0, stdout="", stderr="collector blocked" if failed else "")

    engine = OnboardingEngine(
        execute=True,
        command_runner=runner,
        set_evidence_collector=lambda _key: {
            "catalog_only": False,
            "supports_opening_simulation": False,
            "image_coverage": 1.0,
            "resolved_market_date": "2026-09-22",
        },
    )
    outcome = engine.run_step(_job("images"))
    assert outcome.kind == "retry"
    assert outcome.error_code == "collector_membership_refresh_failed"
