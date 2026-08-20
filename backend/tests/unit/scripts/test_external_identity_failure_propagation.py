from backend.db.repositories.card_variant_repository import ExternalVariantIdentityConflict
from backend.db.services.scrape_failure_classification import (
    ERROR_EXTERNAL_VARIANT_IDENTITY_CONFLICT,
)
from backend.scripts import run_pokemon_set_scrape as runner


def test_deterministic_identity_conflict_is_not_retried_internally(monkeypatch):
    calls = []

    class Scraper:
        enable_db_ingestion = True

        def scrape(self, *_args):
            calls.append(1)
            raise ExternalVariantIdentityConflict(
                "external identity contradicts incoming variant"
            )

    class Config:
        PRINTED_TOTAL = 102

    monkeypatch.setattr(runner, "_backoff_sleep", lambda *_: None)
    result = runner._scrape_one_set(
        Scraper(), Config, "base", 1, 1, "2026-08-19"
    )

    assert len(calls) == 1
    assert result["status"] == "failed"
    assert result["error_code"] == ERROR_EXTERNAL_VARIANT_IDENTITY_CONFLICT
