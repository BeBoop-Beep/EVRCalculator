import json
from pathlib import Path
from subprocess import CompletedProcess

from backend.services import pokemon_set_onboarding_service as service
from backend.services.pokemon_set_config_generation_service import GeneratedConfig
from backend.services.pokemon_onboarding_git_service import GitSettings


def test_mocked_onboarding_reaches_completed_without_manual_gate_metadata(monkeypatch, tmp_path):
    api_set = {
        "id": "api5", "name": "Future Set", "series": "Mega Evolution",
        "releaseDate": "2026/08/01", "printedTotal": 10, "total": 12,
        "ptcgoCode": "FUT", "images": {"symbol": "s", "logo": "l"},
    }
    monkeypatch.setattr(service, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(service, "fetch_targeted_sets", lambda *a, **k: [api_set])
    config = tmp_path / "backend/constants/tcg/pokemon/megaEvolutionEra/futureSet.py"
    config.parent.mkdir(parents=True)

    def generate(*args, **kwargs):
        config.write_text('PULL_MODEL_STATUS = "pending"\nUSE_MONTE_CARLO_V2 = False\nPULL_RATE_MAPPING = {}\n')
        set_map = config.parent / "setMap.py"
        set_map.write_text("SET_CONFIG_MAP = {}\nSET_ALIAS_MAP = {}\n")
        return GeneratedConfig("futureSet", "megaEvolutionEra", config, set_map, (config, set_map))

    monkeypatch.setattr(service, "generate_one_set_config", generate)
    monkeypatch.setattr(service.GitAdapter, "prepare_worktree", lambda self, key, phase="source": (tmp_path, f"branch-{phase}"))
    monkeypatch.setattr(service.GitAdapter, "commit_expected_files", lambda *a, **k: "sha")
    monkeypatch.setattr(service.GitAdapter, "push_and_open_pr", lambda *a, **k: {
        "status": "source_pr_open", "source_pr_url": "https://pr/1", "source_pr_number": 1,
    })
    monkeypatch.setattr(
        service.GitAdapter, "reconcile_pr_and_optional_deploy",
        lambda *a, **k: {"status": "deployed"},
    )
    monkeypatch.setattr(service, "apply_approved_pull_model", lambda *a, **k: config)
    monkeypatch.setattr(service, "validate_deployed_pull_model", lambda *a, **k: {
        "pull_model_status": "approved", "use_monte_carlo_v2": True,
    })

    simulation_calls = {"n": 0}
    def command_runner(command, **kwargs):
        if "--dry-run" in command and "run_all_v2_sets.py" in " ".join(command):
            payload = {"matched_set_count": 1, "matched_sets": [{
                "canonical_key": "futureSet", "use_monte_carlo_v2": True,
                "pull_model_status": "approved",
            }]}
            return CompletedProcess(command, 0, stdout="SIMULATION_JSON=" + json.dumps(payload), stderr="")
        return CompletedProcess(command, 0, stdout="", stderr="")

    def sim_evidence(client, set_id):
        simulation_calls["n"] += 1
        return {
            "run_id": "old" if simulation_calls["n"] == 1 else "new",
            "target_id": "set", "details_complete": True,
        }

    evidence = {
        "set_id": "set", "public_set_correct": True, "ready_for_daily_scrape": True,
        "cards_populated": True, "variants_populated": True, "market_prices_populated": True,
        "resolved_market_date": "2026-08-01", "positive_standard_set_value": True,
        "image_coverage": 1.0, "rarity_census": {
            "common": 4, "uncommon": 3, "rare": 1, "hit": 1,
        },
    }
    complete = {name: True for name in (
        "source_config_registered", "public_set_correct", "ready_for_daily_scrape",
        "cards_populated", "variants_populated", "market_prices_populated",
        "image_coverage_acceptable", "positive_standard_set_value", "approved_pull_model",
        "current_simulation", "simulation_details", "current_desirability_components",
        "canonical_ca7", "overall_rip", "current_opvc", "current_top_chase",
        "explore_contains_set", "set_page_snapshot", "source_dates_align",
        "no_mixed_generation_warning", "no_satisfiable_missing_input_warning",
    )}
    engine = service.OnboardingEngine(
        execute=True, command_runner=command_runner,
        git_settings=GitSettings(mode="pr", worktree_dir=tmp_path),
        set_evidence_collector=lambda key: dict(evidence),
        simulation_evidence_collector=sim_evidence, db_client=object(),
        publication_evaluator=lambda *a, **k: {
            "complete": True, "dates_aligned": True, "reason_code": "allowed_complete",
        },
        verification_collector=lambda *a, **k: {**complete, "complete": True, "missing": []},
    )
    job = {
        "id": "job", "source_set_name": "Future Set", "source_set_id": "999",
        "current_step": "metadata_resolution", "metadata_json": {
            "card_details_url": "cards", "sealed_details_url": "sealed",
        },
    }

    pull_manifest = tmp_path / "rates.json"
    pull_manifest.write_text(json.dumps({
        "provenance": {"source_urls": ["https://source"]}, "captured_date": "2026-08-01",
        "rarity_denominators": {"hit": 10}, "product_type": "standard_booster",
        "collation_compatibility_approved": True, "pack_state_overrides": {},
        "slot_assumptions": {
            "reverse_slot_probabilities": {"slot_1": {"regular reverse": 1.0}},
            "rare_slot_probability": {"rare": 1.0},
        },
        "validation": {
            "no_pack_odds_scaling_error": True, "valid_pack_state_override": True,
            "supported_product_collation": True, "all_required_rarities_classified": True,
        },
    }))

    waits = []
    for _ in range(30):
        outcome = engine.run_step(job)
        current = job["current_step"]
        job["metadata_json"].setdefault("steps", {})[current] = dict(outcome.evidence)
        for field in ("canonical_key", "era_folder", "source_pr_url"):
            if field in outcome.evidence:
                job[field] = outcome.evidence[field]
        if outcome.error_code == "awaiting_pull_rates":
            waits.append(outcome.error_code)
            engine.pull_rates_file = pull_manifest
            continue
        if outcome.kind == "wait":
            waits.append(outcome.error_code)
            job["current_step"] = outcome.step
            continue
        if outcome.kind == "advance":
            job["current_step"] = outcome.step
            continue
        assert outcome.kind == "complete"
        break
    assert outcome.kind == "complete"
    assert "awaiting_pull_rates" in waits
    assert "publication_gate" not in job["metadata_json"]
    assert "final_verification" not in job["metadata_json"]
