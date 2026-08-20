import pytest

from backend.db.services.market_run_evidence import (
    qualifying_set_ids_for_date,
    resolve_run_set_id,
    run_metrics_qualify,
)


def _run(**overrides):
    base = {
        "job_name": "pokemon_set_scrape",
        "source_system": "tcgplayer",
        "job_type": "price_scrape",
        "entity_type": "set",
        "status": "success",
        "market_date": "2026-08-19",
        "items_succeeded": 1,
        "items_failed": 0,
        "metadata": {
            "sourceCoverageRatio": 1,
            "acceptedVariantGroups": 12,
            "positiveNmObservationCount": 12,
        },
    }
    base.update(overrides)
    return base


def test_canonical_qualifying_run_passes():
    assert run_metrics_qualify(_run()) is True


def test_wrong_job_family_never_qualifies():
    assert run_metrics_qualify(_run(source_system="pokemontcgio")) is False
    assert run_metrics_qualify(_run(job_name="pokemon_set_backfill")) is False
    assert run_metrics_qualify(_run(job_type="catalog_scrape")) is False
    assert run_metrics_qualify(_run(entity_type="card")) is False


def test_non_success_or_failed_items_never_qualify():
    assert run_metrics_qualify(_run(status="partial_failure")) is False
    assert run_metrics_qualify(_run(items_failed=1)) is False
    assert run_metrics_qualify(_run(items_succeeded=0)) is False


def test_partial_coverage_never_qualifies():
    assert run_metrics_qualify(
        _run(metadata={"sourceCoverageRatio": 0.99,
                       "acceptedVariantGroups": 12,
                       "positiveNmObservationCount": 12})) is False


def test_zero_accepted_variant_groups_never_qualifies():
    assert run_metrics_qualify(
        _run(metadata={"sourceCoverageRatio": 1,
                       "acceptedVariantGroups": 0,
                       "positiveNmObservationCount": 0})) is False


def test_insufficient_positive_observations_never_qualifies():
    assert run_metrics_qualify(
        _run(metadata={"sourceCoverageRatio": 1,
                       "acceptedVariantGroups": 12,
                       "positiveNmObservationCount": 11})) is False


@pytest.mark.parametrize("metadata", [
    None, {}, {"sourceCoverageRatio": "not-a-number",
               "acceptedVariantGroups": 1, "positiveNmObservationCount": 1},
    {"acceptedVariantGroups": 1, "positiveNmObservationCount": 1},
    "a string, not a mapping",
])
def test_malformed_or_missing_metrics_never_qualify(metadata):
    assert run_metrics_qualify(_run(metadata=metadata)) is False


def test_queue_linked_run_resolves_through_scrape_jobs():
    run = _run(queue_job_id=41)
    assert resolve_run_set_id(run, {41: "set-alpha"}) == "set-alpha"


def test_queue_linked_run_with_unknown_job_resolves_to_nothing():
    # A queue link that does not resolve is NOT downgraded to the metadata
    # fallback: the link is the authority and it failed.
    run = _run(queue_job_id=999, metadata={**_run()["metadata"], "set_id": "set-alpha"})
    assert resolve_run_set_id(run, {41: "set-alpha"}) is None


def test_null_queue_job_run_resolves_through_explicit_metadata_set_id():
    run = _run(queue_job_id=None,
               metadata={**_run()["metadata"], "set_id": "set-alpha"})
    assert resolve_run_set_id(run, {}) == "set-alpha"


def test_null_queue_job_run_without_explicit_identity_resolves_to_nothing():
    run = _run(queue_job_id=None)
    assert resolve_run_set_id(run, {}) is None


def test_set_identity_is_never_inferred_from_names():
    run = _run(queue_job_id=None,
               metadata={**_run()["metadata"], "set_name": "Base Set"})
    assert resolve_run_set_id(run, {}) is None


def test_set_filter_alone_is_not_an_identity():
    # set_filter is an operator-supplied filter list, not a set identity.
    run = _run(queue_job_id=None,
               metadata={**_run()["metadata"], "set_filter": ["baseSet"],
                         "items_selected": 1})
    assert resolve_run_set_id(run, {}) is None


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows
        self._page = None

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def eq(self, column, value):
        return _Query([row for row in self._rows if row.get(column) == value])

    def in_(self, column, values):
        return _Query([row for row in self._rows if row.get(column) in values])

    def range(self, start, end):
        self._page = (start, end)
        return self

    def execute(self):
        start, end = self._page if self._page else (0, len(self._rows))
        return _Result(self._rows[start:end + 1])


class _Client:
    def __init__(self, tables):
        self._tables = tables

    def table(self, name):
        return _Query(list(self._tables.get(name, [])))


def test_wrong_date_run_does_not_satisfy_readiness():
    client = _Client({"scrape_job_runs": [_run(queue_job_id=41, market_date="2026-08-18")],
                      "scrape_jobs": [{"id": 41, "set_id": "set-alpha"}]})
    assert qualifying_set_ids_for_date(client, "2026-08-19") == set()


def test_wrong_set_run_credits_only_its_own_set():
    client = _Client({"scrape_job_runs": [_run(queue_job_id=41)],
                      "scrape_jobs": [{"id": 41, "set_id": "set-beta"}]})
    assert qualifying_set_ids_for_date(client, "2026-08-19") == {"set-beta"}


def test_null_queue_link_with_explicit_identity_is_credited():
    run = _run(queue_job_id=None, metadata={"sourceCoverageRatio": 1,
                                            "acceptedVariantGroups": 5,
                                            "positiveNmObservationCount": 5,
                                            "set_id": "set-gamma"})
    client = _Client({"scrape_job_runs": [run], "scrape_jobs": []})
    assert qualifying_set_ids_for_date(client, "2026-08-19") == {"set-gamma"}


def test_non_qualifying_metrics_are_dropped_at_the_query_seam():
    run = _run(queue_job_id=41, metadata={"sourceCoverageRatio": 0.5,
                                          "acceptedVariantGroups": 5,
                                          "positiveNmObservationCount": 5})
    client = _Client({"scrape_job_runs": [run],
                      "scrape_jobs": [{"id": 41, "set_id": "set-alpha"}]})
    assert qualifying_set_ids_for_date(client, "2026-08-19") == set()
