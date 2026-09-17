from pathlib import Path


def test_post_scrape_wrapper_invokes_resilient_audit_as_module():
    root = Path(__file__).resolve().parents[4]
    wrapper = (root / "backend/scripts/rebuild_snapshots_after_scrape.sh").read_text(encoding="utf-8")
    assert 'RESILIENT_AUDIT_MODULE="backend.scripts.audit_pokemon_market_publication_resilient"' in wrapper
    assert '"${PYTHON_BIN}" -m "${RESILIENT_AUDIT_MODULE}"' in wrapper
