"""Parity and streaming-memory tests for the V2 fused dual search."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from backend.calculations.evr.best_open_price import (
    BestOpenPriceSearchError,
    COMPARISON_AUTHORITY_FINANCIAL_V4,
    COMPARISON_AUTHORITY_OVERALL_V12,
    ExactBestOpenPriceSearch,
    quantity_price_interval_cents,
)
from backend.calculations.evr.best_open_price_v2_fused import DualBestOpenPriceSearch


@dataclass
class _FakeCandidate:
    product_id: str
    quantity: int
    score_calls: list[tuple[int, int]]
    _last_comparator_seconds: float = field(default=0.0, init=False)

    def score_candidate(self, price_cents: int):
        self.score_calls.append((self.quantity, price_cents))
        return {
            "sealedProductId": self.product_id,
            "priceCents": price_cents,
            "quantity": self.quantity,
            "targetBudget": 10.0,
            "actualCommittedCapital": self.quantity * (price_cents / 100.0),
            "financialRipV3Score": float(price_cents),
            "financialRipV4Score": float(price_cents),
            "overallRipV12Score": float(price_cents),
            "overallRipV12Rankable": True,
            "chanceToRecoverCapital": 0.5,
            "scoringSeconds": 0.0,
        }

    def compare(self, score_record, benchmark, *, authority=COMPARISON_AUTHORITY_OVERALL_V12):
        self._last_comparator_seconds = 0.0
        # Synthetic exact surface: the candidate wins at/below the authority's
        # frozen threshold and loses above it.  Both leader and non-leader
        # domains therefore have an unambiguous global maximum.
        return int(score_record["priceCents"]) <= int(benchmark["thresholdCents"])

    def evaluate(self, price_cents, benchmark, *, comparison_authority=COMPARISON_AUTHORITY_OVERALL_V12):
        record = self.score_candidate(price_cents)
        wins = self.compare(record, benchmark, authority=comparison_authority)
        return {
            **record,
            "wins": wins,
            "comparatorSeconds": 0.0,
            "comparisonAuthority": comparison_authority,
        }


def _factory(score_calls):
    def prepare(quantity: int):
        return _FakeCandidate("candidate", quantity, score_calls)
    return prepare


def _oracle(*, current_rank, benchmark, authority, current_price=500, budget=1000):
    score_calls = []
    return ExactBestOpenPriceSearch(
        product_id="candidate",
        budget_cents=budget,
        current_price_cents=current_price,
        current_quantity=budget // current_price,
        current_rank=current_rank,
        benchmark=benchmark,
        prepare_quantity=_factory(score_calls),
        source_authority_fingerprint="fp",
        expected_source_authority_fingerprint="fp",
        max_quantity_to_construct=budget,
        comparison_authority=authority,
    ).search()


@pytest.mark.parametrize(
    "rip_rank,rip_threshold,financial_rank,financial_threshold",
    [
        (2, 450, 2, 420),      # both non-leaders
        (1, 780, 1, 720),      # both leaders
        (2, 450, 1, 780),      # RIP non-leader, Financial leader
        (1, 760, 2, 430),      # RIP leader, Financial non-leader
    ],
)
def test_fused_thresholds_match_two_independent_exact_oracles(
    rip_rank, rip_threshold, financial_rank, financial_threshold,
):
    rip_benchmark = {"sealedProductId": "rip-bench", "thresholdCents": rip_threshold}
    financial_benchmark = {"sealedProductId": "fin-bench", "thresholdCents": financial_threshold}
    score_calls = []
    fused = DualBestOpenPriceSearch(
        product_id="candidate",
        budget_cents=1000,
        current_price_cents=500,
        current_quantity=2,
        rip_current_rank=rip_rank,
        rip_benchmark=rip_benchmark,
        financial_current_rank=financial_rank,
        financial_benchmark=financial_benchmark,
        prepare_quantity=_factory(score_calls),
        source_authority_fingerprint="fp",
        expected_source_authority_fingerprint="fp",
        max_quantity_to_construct=1000,
    ).search()

    rip_oracle = _oracle(
        current_rank=rip_rank,
        benchmark=rip_benchmark,
        authority=COMPARISON_AUTHORITY_OVERALL_V12,
    )
    financial_oracle = _oracle(
        current_rank=financial_rank,
        benchmark=financial_benchmark,
        authority=COMPARISON_AUTHORITY_FINANCIAL_V4,
    )

    assert fused["ripResult"]["threshold"]["priceCents"] == rip_oracle["threshold"]["priceCents"]
    assert fused["financialResult"]["threshold"]["priceCents"] == financial_oracle["threshold"]["priceCents"]
    assert fused["ripResult"]["threshold"]["quantity"] == rip_oracle["threshold"]["quantity"]
    assert fused["financialResult"]["threshold"]["quantity"] == financial_oracle["threshold"]["quantity"]
    assert fused["ripResult"]["exactness"]["thresholdWins"] is True
    assert fused["ripResult"]["exactness"]["oneCentMaximal"] is True
    assert fused["financialResult"]["exactness"]["thresholdWins"] is True
    assert fused["financialResult"]["exactness"]["oneCentMaximal"] is True


def test_fused_search_scores_shared_prices_once_and_has_no_score_cache_evictions():
    score_calls = []
    result = DualBestOpenPriceSearch(
        product_id="candidate",
        budget_cents=1000,
        current_price_cents=500,
        current_quantity=2,
        rip_current_rank=2,
        rip_benchmark={"sealedProductId": "rip-bench", "thresholdCents": 420},
        financial_current_rank=2,
        financial_benchmark={"sealedProductId": "fin-bench", "thresholdCents": 430},
        prepare_quantity=_factory(score_calls),
        source_authority_fingerprint="fp",
        expected_source_authority_fingerprint="fp",
        max_quantity_to_construct=1000,
    ).search()
    diagnostics = result["diagnostics"]
    assert diagnostics["uniqueCandidatePricesScored"] == len(score_calls)
    assert diagnostics["naiveScoreCount"] > diagnostics["uniqueCandidatePricesScored"]
    assert diagnostics["scoreReuseSavings"] > 0
    assert diagnostics["scoreCacheHits"] == diagnostics["scoreReuseSavings"]
    assert diagnostics["scoreCacheEvictions"] == 0
    assert diagnostics["fusedStreaming"] is True


def test_fused_search_streams_singleton_quantity_builds_and_keeps_one_resident():
    score_calls = []
    batch_widths = []

    def prepare_batch(quantities):
        batch_widths.append(len(quantities))
        return {q: _FakeCandidate("candidate", q, score_calls) for q in quantities}

    result = DualBestOpenPriceSearch(
        product_id="candidate",
        budget_cents=1000,
        current_price_cents=500,
        current_quantity=2,
        rip_current_rank=2,
        rip_benchmark={"sealedProductId": "rip-bench", "thresholdCents": 105},
        financial_current_rank=2,
        financial_benchmark={"sealedProductId": "fin-bench", "thresholdCents": 100},
        prepare_quantity=_factory(score_calls),
        prepare_quantities=prepare_batch,
        source_authority_fingerprint="fp",
        expected_source_authority_fingerprint="fp",
        max_quantity_to_construct=20,
    ).search()

    diagnostics = result["diagnostics"]
    assert diagnostics["uniqueQuantitiesConstructed"] > 4
    assert diagnostics["maximumResidentSharedQuantities"] == 1
    assert diagnostics["scoreCacheEvictions"] == 0
    assert batch_widths and max(batch_widths) == 1


def test_fused_nonleader_respects_max_quantity_domain_and_can_remain_unresolved():
    result = DualBestOpenPriceSearch(
        product_id="candidate",
        budget_cents=1000,
        current_price_cents=500,
        current_quantity=2,
        rip_current_rank=2,
        rip_benchmark={"sealedProductId": "rip-bench", "thresholdCents": 100},
        financial_current_rank=2,
        financial_benchmark={"sealedProductId": "fin-bench", "thresholdCents": 100},
        prepare_quantity=_factory([]),
        source_authority_fingerprint="fp",
        expected_source_authority_fingerprint="fp",
        max_quantity_to_construct=4,
    ).search()
    assert result["ripResult"]["status"] == "unresolved_extreme_quantity"
    assert result["financialResult"]["status"] == "unresolved_extreme_quantity"


def test_fused_leader_fails_closed_when_current_market_does_not_reconstruct_as_number_one():
    search = DualBestOpenPriceSearch(
        product_id="candidate",
        budget_cents=1000,
        current_price_cents=500,
        current_quantity=2,
        rip_current_rank=1,
        rip_benchmark={"sealedProductId": "rip-bench", "thresholdCents": 499},
        financial_current_rank=2,
        financial_benchmark={"sealedProductId": "fin-bench", "thresholdCents": 400},
        prepare_quantity=_factory([]),
        source_authority_fingerprint="fp",
        expected_source_authority_fingerprint="fp",
        max_quantity_to_construct=1000,
    )
    with pytest.raises(BestOpenPriceSearchError, match="current rip leader"):
        search.search()


def test_fused_search_fails_closed_on_source_authority_fingerprint_mismatch():
    with pytest.raises(BestOpenPriceSearchError, match="fingerprint mismatch"):
        DualBestOpenPriceSearch(
            product_id="candidate",
            budget_cents=1000,
            current_price_cents=500,
            current_quantity=2,
            rip_current_rank=2,
            rip_benchmark={"sealedProductId": "rip-bench", "thresholdCents": 400},
            financial_current_rank=2,
            financial_benchmark={"sealedProductId": "fin-bench", "thresholdCents": 400},
            prepare_quantity=_factory([]),
            source_authority_fingerprint="wrong",
            expected_source_authority_fingerprint="expected",
        )


def test_explicit_authorities_share_one_price_stream_and_one_quantity_build():
    calls = []
    batches = []

    class Candidate(_FakeCandidate):
        def compare(self, score_record, benchmark, *, authority):
            assert authority in {"overall_financial_v5_shadow", "financial_v5_candidate"}
            return super().compare(score_record, benchmark, authority=authority)

    def batch(quantities):
        batches.append(tuple(quantities))
        return {q: Candidate("candidate", q, calls) for q in quantities}

    result = DualBestOpenPriceSearch(
        product_id="candidate", budget_cents=1000, current_price_cents=500,
        current_quantity=2, rip_current_rank=2,
        rip_benchmark={"sealedProductId": "overall", "thresholdCents": 105},
        financial_current_rank=2,
        financial_benchmark={"sealedProductId": "financial", "thresholdCents": 100},
        prepare_quantity=lambda q: Candidate("candidate", q, calls),
        prepare_quantities=batch, source_authority_fingerprint="fp",
        expected_source_authority_fingerprint="fp", max_quantity_to_construct=20,
        rip_comparison_authority="overall_financial_v5_shadow",
        financial_comparison_authority="financial_v5_candidate",
        enable_quantity_prefetch=True, quantity_batch_size=3,
    ).search()
    assert result["ripResult"]["threshold"]["priceCents"] == 105
    assert result["financialResult"]["threshold"]["priceCents"] == 100
    assert result["ripResult"]["threshold"]["comparisonAuthority"] == "overall_financial_v5_shadow"
    assert result["financialResult"]["threshold"]["comparisonAuthority"] == "financial_v5_candidate"
    assert result["diagnostics"]["uniqueCandidatePricesScored"] == len(calls)
    assert len(calls) == len(set(calls))
    assert any(len(q) > 1 for q in batches)
    assert max(map(len, batches)) <= 3
    assert result["diagnostics"]["maximumPendingBatchCandidates"] <= 3


def test_prefetch_excludes_quantities_with_no_reachable_cent():
    batches = []

    def batch(quantities):
        batches.append(tuple(quantities))
        return {q: _FakeCandidate("candidate", q, []) for q in quantities}

    result = DualBestOpenPriceSearch(
        product_id="candidate", budget_cents=1000, current_price_cents=500,
        current_quantity=2, rip_current_rank=2,
        rip_benchmark={"sealedProductId": "r", "thresholdCents": 18},
        financial_current_rank=2,
        financial_benchmark={"sealedProductId": "f", "thresholdCents": 18},
        prepare_quantity=lambda q: _FakeCandidate("candidate", q, []),
        prepare_quantities=batch, source_authority_fingerprint="fp",
        expected_source_authority_fingerprint="fp", max_quantity_to_construct=60,
        enable_quantity_prefetch=True, quantity_batch_size=8,
    ).search()
    assert result["ripResult"]["threshold"]["priceCents"] == 18
    assert any(any(q > 40 for q in block) for block in batches)
    for block in batches:
        if block == (2,):  # current market singleton precedes the low domain
            continue
        for q in block:
            low, high = quantity_price_interval_cents(1000, q)
            assert low <= high < 500
