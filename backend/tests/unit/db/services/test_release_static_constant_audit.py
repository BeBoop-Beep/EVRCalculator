"""Static audit: where the canonical constants and the Ranking / Best-Open method versions may be read.

A new reader of a static canonical constant, or a new serving reader of a Ranking / Best-Open snapshot that does not
go through the active release, fails here and must be classified deliberately.
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]

CANONICAL_TOKEN = re.compile(
    r"CANONICAL_OVERALL_RIP_VERSION|CANONICAL_FINANCIAL_RIP_VERSION|canonical_public_rip_contract_version\(|"
    r"canonical_overall_rip_target_key\(|canonical_public_rip_contract_target_key\(")

# file -> classification of why it may read the STATIC canonical selection.
CLASSIFIED = {
    # the constants' own definitions / identity authority
    "backend/desirability/scoring_config.py": "scoring-definition",
    "backend/db/services/public_rip_publication_contract.py": "identity-authority (canonical + candidate identities)",
    # scoring / contract builders: they compute a model, they do not choose which one is live
    "backend/desirability/public_rip_contract_v7.py": "historical-contract",
    "backend/desirability/public_rip_contract_v8.py": "historical-contract",
    "backend/desirability/public_rip_contract_v9.py": "historical-contract",
    "backend/desirability/public_rip_contract_v11.py": "historical-contract",
    "backend/desirability/public_rip_contract_v12.py": "scoring-contract-builder",
    "backend/desirability/weighted_rip.py": "scoring",
    "backend/calculations/evr/financial_rip_v3_config.py": "scoring",
    "backend/calculations/evr/budget_normalized_product_ranking.py": "scoring (comment only)",
    "backend/db/repositories/sealed_product_results_repository.py": "repository (comment only)",
    "backend/db/services/sealed_product_rip_finalization_service.py": "offline-builder (finalization, comment only)",
    "backend/research/chase_pillar_stage6/control.py": "research",
    "backend/research/collector_appeal_candidates.py": "research",
    "backend/db/services/rip_release.py": "release-authority (static = marked fallback bundle only)",
    # serving readers: the static value is ONLY the marked fallback for an unreadable pointer
    "backend/db/services/product_family_rankings_service.py": "serving: release-driven; static = marked fallback",
    "backend/db/services/set_rip_service.py": "serving: release-driven; static = marked fallback",
    "backend/db/services/pokemon_sealed_product_detail_service.py": "serving (comment only; release-driven)",
    # KNOWN GAP (Prompt 5E): the Rankings snapshot BUILDER/PUBLISHER stamps and selects on the static canonical
    # identity. It is not a request-time reader, and a snapshot it builds under V12 is judged stale by the
    # release-aware reader after a V14 flip (fail closed), but it cannot yet BUILD a V14-stamped snapshot.
    "backend/db/services/explore_rip_statistics_service.py": "BUILDER-NOT-RELEASE-DRIVEN (gap)",
    "backend/db/services/rankings_publication_lifecycle.py": "BUILDER-NOT-RELEASE-DRIVEN (gap)",
}
KNOWN_GAPS = {p for p, why in CLASSIFIED.items() if "gap" in why}


def _tracked(pattern_files):
    out = subprocess.run(["git", "grep", "-l", "-E", pattern_files, "--", "backend", ":!backend/tests", ":!backend/scripts",
                          ":!backend/db/migrations"], cwd=ROOT, capture_output=True, text=True).stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


def test_every_static_canonical_reader_is_classified():
    found = _tracked(CANONICAL_TOKEN.pattern)
    unclassified = sorted(f for f in found if f not in CLASSIFIED)
    assert not unclassified, "classify these static canonical readers (scoring / builder / historical / serving): %s" % unclassified


def test_the_known_builder_gap_is_exactly_the_two_rankings_publication_files():
    assert KNOWN_GAPS == {"backend/db/services/explore_rip_statistics_service.py",
                          "backend/db/services/rankings_publication_lifecycle.py"}


def test_ranking_and_best_open_snapshots_are_read_only_by_release_driven_services():
    token = r"load_best_open_price_(ranking|product)\(|load_full_market_ranking\(|load_budget_ranking\("
    readers = _tracked(token)
    allowed = {
        "backend/db/services/budget_product_best_open_price_service.py",   # the loaders themselves
        "backend/db/services/budget_product_ranking_service.py",
        "backend/db/services/public_overall_product_rankings_service.py",  # release-driven
        "backend/db/services/pokemon_sealed_product_detail_service.py",    # release-driven
    }
    assert readers <= allowed, sorted(readers - allowed)
    for served in ("public_overall_product_rankings_service", "pokemon_sealed_product_detail_service"):
        text = (ROOT / "backend/db/services" / (served + ".py")).read_text(encoding="utf-8")
        assert "rip_release" in text and "best_open_method_versions" in text
