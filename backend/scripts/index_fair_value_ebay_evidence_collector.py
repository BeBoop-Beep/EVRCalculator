"""Shadow-only bounded eBay Browse evidence collector.

Raw capture -> versioned matcher output -> future fair value model.

This module ONLY produces `active_ask` evidence and versioned matcher
diagnostics. It never writes public prices, Set Value, or simulation
inputs, and it never asserts a sale occurred. See
`backend/artifacts/index_fair_value/EBAY_EVIDENCE_COLLECTOR_D1_SHADOW.md`
for the accompanying implementation report.
"""
from __future__ import annotations

import base64
import hashlib
import json
from decimal import Decimal, InvalidOperation
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from backend.scripts import ebay_d3_matcher_v3 as matcher
from backend.scripts import ebay_d3_matcher_v5 as pricing_matcher
from backend.scripts.ebay_language_policy_v1 import evaluate_structured_aspect as evaluate_language
from backend.scripts.index_fair_value_ebay_supply import build_query, normalize

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_DIR = ROOT / "backend/artifacts/index_fair_value"
RUNS_DIR = ARTIFACTS_DIR / "ebay_evidence_runs"

QUERY_STRATEGY_VERSION = "ebay_evidence_query_strategy_v1"
COLLECTOR_VERSION = "ebay_evidence_collector_v1"
EVIDENCE_KIND = "active_ask"
MATCHER_VERSION = matcher.MATCHER_VERSION

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
AUTH_EXPIRED_STATUS = {401}


class BudgetExhausted(RuntimeError):
    """Raised internally when the run-level request budget is exhausted."""


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CollectorConfig:
    max_requests_per_day: int = 1000
    max_requests_per_run: int = 1000
    max_pages_per_search: int = 3
    max_listings_per_target: int = 200
    retry_budget: int = 5
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 30.0
    run_matcher: bool = True

    def __post_init__(self) -> None:
        if self.max_requests_per_run > self.max_requests_per_day:
            object.__setattr__(self, "max_requests_per_run", self.max_requests_per_day)


# --------------------------------------------------------------------------
# Credentials (reuses the frontend/.env.local convention from the D1 script)
# --------------------------------------------------------------------------


def load_ebay_env(env_path: Path | None = None) -> dict[str, str]:
    path = env_path or (ROOT / "frontend/.env.local")
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def redact(value: str | None) -> str:
    if not value:
        return "<empty>"
    return f"<redacted:{len(value)}>"


class TokenProvider:
    """Fetches and caches an OAuth2 client_credentials token; never logs secrets."""

    def __init__(self, cfg: Mapping[str, str], fetch: Callable[..., Any] | None = None) -> None:
        self._cfg = cfg
        self._token: str | None = None
        self._fetch = fetch or self._http_fetch

    def _http_fetch(self) -> str:
        client_id = self._cfg.get("EBAY_CLIENT_ID", "")
        client_secret = self._cfg.get("EBAY_CLIENT_SECRET", "")
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        req = urllib.request.Request(
            TOKEN_URL,
            data=b"grant_type=client_credentials&scope=https%3A%2F%2Fapi.ebay.com%2Foauth%2Fapi_scope",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)["access_token"]
        except Exception as exc:  # pragma: no cover - network path, sanitized re-raise
            raise RuntimeError(f"token_fetch_failed:{type(exc).__name__}") from exc

    def get(self, force_refresh: bool = False) -> str:
        if self._token is None or force_refresh:
            self._token = self._fetch()
        return self._token


# --------------------------------------------------------------------------
# Query generation (centralized; every emitted query is provenance-tracked)
# --------------------------------------------------------------------------


def generate_queries(target: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Deterministic, centralized query generation. Always emits the same
    formulations for the same target -- allocation never depends on result size.
    """
    primary = build_query(target)
    number = str(target.get("card_number") or "").strip()
    name = str(target.get("card_name") or "").strip()
    set_name = str(target.get("set_name") or "").strip()
    broad_terms = [name, number, set_name]
    broad_query = " ".join(x for x in broad_terms if x)
    formulations = [
        {"formulation": "primary", **primary},
        {
            "formulation": "collector_number_focus",
            "query": broad_query,
            "marketplace": "EBAY_US",
            "category_id": "183454",
            "limit": 100,
            "filters": "buyingOptions:{FIXED_PRICE|AUCTION}",
            "version": QUERY_STRATEGY_VERSION,
        },
    ]
    if formulations[0]["query"] == formulations[1]["query"]:
        formulations = formulations[:1]
    return formulations


def _search_url(query: Mapping[str, Any]) -> str:
    params = urllib.parse.urlencode(
        {"q": query["query"], "category_ids": query["category_id"], "limit": query["limit"], "filter": query["filters"]}
    )
    return f"{BROWSE_SEARCH_URL}?{params}"


# --------------------------------------------------------------------------
# Cohort selection
# --------------------------------------------------------------------------


def select_cohort(
    name: str = "d1_70",
    target_file: Path | str | None = None,
    explicit_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    if target_file is not None:
        rows = json.loads(Path(target_file).read_text(encoding="utf-8"))
        cards = rows["cards"] if isinstance(rows, dict) and "cards" in rows else rows
    elif name == "d1_70":
        cohort = json.loads((ARTIFACTS_DIR / "ebay_pilot_cohort.json").read_text(encoding="utf-8"))
        cards = cohort["cards"]
    else:
        raise ValueError(f"unknown cohort: {name}")
    cards = list(cards)
    if explicit_ids is not None:
        wanted = set(explicit_ids)
        cards = [c for c in cards if c.get("canonical_card_id") in wanted]
    return sorted(cards, key=lambda c: str(c.get("canonical_card_id")))


def cohort_fingerprint(cards: Iterable[Mapping[str, Any]]) -> str:
    ids = sorted(str(c.get("canonical_card_id")) for c in cards)
    return hashlib.sha256("|".join(ids).encode()).hexdigest()


# --------------------------------------------------------------------------
# HTTP with bounded retry/backoff
# --------------------------------------------------------------------------


@dataclass
class RequestOutcome:
    ok: bool
    data: dict[str, Any] | None = None
    status: int | None = None
    error_type: str | None = None
    retries: int = 0


class BrowseHTTP:
    def __init__(
        self,
        token_provider: TokenProvider,
        config: CollectorConfig,
        opener: Callable[[str, str], Any] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._tokens = token_provider
        self._cfg = config
        self._opener = opener or self._urllib_opener
        self._sleep = sleep or time.sleep

    @staticmethod
    def _urllib_opener(url: str, token: str) -> dict[str, Any]:
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)

    def _status_of(self, exc: Exception) -> int | None:
        if isinstance(exc, urllib.error.HTTPError):
            return exc.code
        return None

    def get(self, url: str, counters: "RunCounters") -> RequestOutcome:
        if counters.remaining_run_budget <= 0:
            raise BudgetExhausted("run request budget exhausted")
        refreshed_once = False
        attempt = 0
        while True:
            if counters.remaining_run_budget <= 0:
                raise BudgetExhausted("run request budget exhausted")
            counters.requests_attempted += 1
            counters.remaining_run_budget -= 1
            try:
                data = self._opener(url, self._tokens.get())
                counters.requests_successful += 1
                return RequestOutcome(ok=True, data=data, retries=attempt)
            except Exception as exc:  # noqa: BLE001 - classified below
                status = self._status_of(exc)
                if status in AUTH_EXPIRED_STATUS and not refreshed_once:
                    refreshed_once = True
                    self._tokens.get(force_refresh=True)
                    continue
                network_error = status is None and isinstance(exc, (urllib.error.URLError, TimeoutError, OSError))
                if status in RETRYABLE_STATUS or network_error:
                    if attempt >= self._cfg.retry_budget:
                        counters.requests_failed += 1
                        return RequestOutcome(ok=False, status=status, error_type=type(exc).__name__, retries=attempt)
                    counters.retries += 1
                    backoff = min(self._cfg.backoff_max_seconds, self._cfg.backoff_base_seconds * (2**attempt))
                    self._sleep(backoff)
                    attempt += 1
                    continue
                counters.requests_failed += 1
                return RequestOutcome(ok=False, status=status, error_type=type(exc).__name__, retries=attempt)


@dataclass
class RunCounters:
    requests_attempted: int = 0
    requests_successful: int = 0
    requests_failed: int = 0
    retries: int = 0
    remaining_run_budget: int = 1000


# --------------------------------------------------------------------------
# Checkpoint / run state
# --------------------------------------------------------------------------


@dataclass
class RunState:
    run_id: str
    cohort_fingerprint: str
    matcher_version: str
    query_strategy_version: str
    started_at: str
    config: dict[str, Any]
    targets: dict[str, dict[str, Any]] = field(default_factory=dict)
    requests_attempted: int = 0
    requests_successful: int = 0
    requests_failed: int = 0
    retries: int = 0
    last_completed_target: str | None = None
    completed: bool = False

    @classmethod
    def new(cls, run_id: str, cards: list[dict[str, Any]], config: CollectorConfig) -> "RunState":
        return cls(
            run_id=run_id,
            cohort_fingerprint=cohort_fingerprint(cards),
            matcher_version=MATCHER_VERSION,
            query_strategy_version=QUERY_STRATEGY_VERSION,
            started_at=datetime.now(timezone.utc).isoformat(),
            config=config.__dict__.copy(),
            targets={c["canonical_card_id"]: {"status": "pending"} for c in cards},
        )

    def path(self) -> Path:
        return RUNS_DIR / f"{self.run_id}.json"

    def save(self) -> None:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self.path().write_text(json.dumps(self.__dict__, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, run_id: str) -> "RunState":
        raw = json.loads((RUNS_DIR / f"{run_id}.json").read_text(encoding="utf-8"))
        return cls(**raw)

    def raw_evidence_path(self) -> Path:
        return RUNS_DIR / f"{self.run_id}.raw.jsonl"

    def match_results_path(self) -> Path:
        return RUNS_DIR / f"{self.run_id}.matches.jsonl"


def _load_seen_item_ids(state: RunState) -> set[str]:
    path = state.raw_evidence_path()
    if not path.exists():
        return set()
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            seen.add(json.loads(line)["ebay_item_id"])
    return seen


def _load_seen_match_keys(state: RunState) -> set[tuple[str, str]]:
    path = state.match_results_path()
    if not path.exists():
        return set()
    seen = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            seen.add((row["target_canonical_card_id"], row["ebay_item_id"]))
    return seen


# --------------------------------------------------------------------------
# Raw evidence normalization (no fabricated fields)
# --------------------------------------------------------------------------


def normalize_listing(item: Mapping[str, Any], *, query: Mapping[str, Any], target: Mapping[str, Any], run_id: str, page: int) -> dict[str, Any]:
    price = (item.get("price") or {}).get("value")
    price_currency = (item.get("price") or {}).get("currency")
    shipping_options = item.get("shippingOptions") or []
    shipping_value = None
    shipping_currency = None
    if shipping_options:
        cost = (shipping_options[0] or {}).get("shippingCost") or {}
        shipping_value = cost.get("value")
        shipping_currency = cost.get("currency")
    try:
        landed = float(Decimal(str(price)) + Decimal(str(shipping_value))) if price is not None and shipping_value is not None and price_currency == shipping_currency else None
    except (InvalidOperation, ValueError):
        landed = None
    return {
        "evidence_kind": EVIDENCE_KIND,
        "ebay_item_id": item.get("itemId"),
        "title": item.get("title"),
        "item_web_url": item.get("itemWebUrl"),
        "image_url": (item.get("image") or {}).get("imageUrl"),
        "price_value": float(price) if price is not None else None,
        "price_currency": price_currency,
        "shipping_value": float(shipping_value) if shipping_value is not None else None,
        "shipping_currency": shipping_currency,
        "landed_ask_value": landed,
        "landed_ask_currency": price_currency if landed is not None else None,
        "condition": item.get("condition"),
        "condition_id": item.get("conditionId"),
        "seller_username": (item.get("seller") or {}).get("username"),
        "buying_options": item.get("buyingOptions") or [],
        "item_location": item.get("itemLocation"),
        "marketplace": "EBAY_US",
        "currency": "USD",
        "search_query": query.get("query"),
        "search_formulation": query.get("formulation"),
        "target_canonical_card_id": target.get("canonical_card_id"),
        "target_card_variant_id": target.get("card_variant_id"),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "collector_run_id": run_id,
        "page": page,
        "collector_version": COLLECTOR_VERSION,
        "raw_item_summary": item,
    }


def run_matcher_on_listing(target: Mapping[str, Any], listing: Mapping[str, Any]) -> dict[str, Any]:
    matcher_target = dict(target)
    matcher_target.setdefault("treatment", target.get("treatment_key"))
    listing_for_matcher = dict(listing.get("raw_item_summary") or {})
    listing_for_matcher.setdefault("condition", listing.get("condition"))
    result = matcher.classify_listing(matcher_target, listing_for_matcher)
    if result.get("identity_state") == "AMBIGUOUS":
        result = dict(result, accepted=False)
    else:
        result = dict(result, accepted=result.get("identity_state") in {"HIGH_CONFIDENCE", "MEDIUM_CONFIDENCE"})
    return {
        "ebay_item_id": listing.get("ebay_item_id"),
        "target_canonical_card_id": target.get("canonical_card_id"),
        "matcher_version": MATCHER_VERSION,
        "match_status": result.get("identity_state"),
        "accepted": result.get("accepted", False),
        "condition_state": result.get("condition_state"),
        "reason": result.get("reason"),
        "diagnostic_features": result.get("evidence"),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "collector_run_id": listing.get("collector_run_id"),
    }


def pricing_eligibility(target: Mapping[str, Any], listing: Mapping[str, Any]) -> dict[str, Any]:
    """Conservative English pricing decision; raw evidence is always retained."""
    item = dict(listing.get("raw_item_summary") or {})
    identity = pricing_matcher.classify_listing(dict(target), item)
    language = evaluate_language(item.get("localizedAspects"), expected_language="ENGLISH")
    identity_ok = identity.get("identity_state") == "HIGH_CONFIDENCE"
    if not identity_ok:
        status = "IDENTITY_REJECTED"
    elif language.language_state == "LANGUAGE_MISMATCH":
        status = "NON_ENGLISH_EXCLUDED"
    elif language.language_state == "LANGUAGE_MATCH":
        status = "ENGLISH_ELIGIBLE"
    else:
        status = "LANGUAGE_UNRESOLVED"
    return {"eligibility_status": status, "identity_qualified": identity_ok,
            "identity_state": identity.get("identity_state"), "identity_reason": identity.get("reason"),
            "identity_matcher_version": pricing_matcher.MATCHER_VERSION,
            "language_state": language.language_state, "language_method_version": language.method_version}


# --------------------------------------------------------------------------
# Collector orchestration
# --------------------------------------------------------------------------


class Collector:
    def __init__(self, http: BrowseHTTP, config: CollectorConfig) -> None:
        self._http = http
        self._cfg = config

    def run(self, state: RunState, cards: list[dict[str, Any]]) -> RunState:
        counters = RunCounters(
            requests_attempted=state.requests_attempted,
            requests_successful=state.requests_successful,
            requests_failed=state.requests_failed,
            retries=state.retries,
            remaining_run_budget=min(self._cfg.max_requests_per_run, self._cfg.max_requests_per_day) - state.requests_attempted,
        )
        seen_items = _load_seen_item_ids(state)
        seen_matches = _load_seen_match_keys(state)
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        raw_fh = state.raw_evidence_path().open("a", encoding="utf-8")
        match_fh = state.match_results_path().open("a", encoding="utf-8")
        try:
            for card in cards:
                target_id = card["canonical_card_id"]
                target_state = state.targets.setdefault(target_id, {"status": "pending"})
                if target_state.get("status") == "completed":
                    continue
                target_state["status"] = "in_progress"
                try:
                    listings_for_target = 0
                    for query in generate_queries(card):
                        if listings_for_target >= self._cfg.max_listings_per_target:
                            break
                        url = _search_url(query)
                        page = 0
                        while url and page < self._cfg.max_pages_per_search:
                            outcome = self._http.get(url, counters)
                            page += 1
                            if not outcome.ok:
                                target_state["last_error"] = {"status": outcome.status, "error_type": outcome.error_type}
                                break
                            data = outcome.data or {}
                            for item in data.get("itemSummaries", []):
                                item_id = item.get("itemId")
                                if not item_id or listings_for_target >= self._cfg.max_listings_per_target:
                                    continue
                                listing = normalize_listing(item, query=query, target=card, run_id=state.run_id, page=page)
                                if item_id not in seen_items:
                                    seen_items.add(item_id)
                                    raw_fh.write(json.dumps(listing, ensure_ascii=False) + "\n")
                                listings_for_target += 1
                                match_key = (target_id, item_id)
                                if self._cfg.run_matcher and match_key not in seen_matches:
                                    seen_matches.add(match_key)
                                    match_result = run_matcher_on_listing(card, listing)
                                    if card.get("pricing_target"):
                                        match_result.update(pricing_eligibility(card, listing))
                                    match_fh.write(json.dumps(match_result, ensure_ascii=False) + "\n")
                            url = data.get("next")
                    target_state["status"] = "completed"
                    target_state["listings_captured"] = listings_for_target
                    state.last_completed_target = target_id
                except BudgetExhausted:
                    target_state["status"] = "deferred"
                    target_state["reason"] = "budget_exhausted"
                    state.requests_attempted = counters.requests_attempted
                    state.requests_successful = counters.requests_successful
                    state.requests_failed = counters.requests_failed
                    state.retries = counters.retries
                    state.completed = False
                    return state
        finally:
            raw_fh.close()
            match_fh.close()
        state.requests_attempted = counters.requests_attempted
        state.requests_successful = counters.requests_successful
        state.requests_failed = counters.requests_failed
        state.retries = counters.retries
        state.completed = all(t.get("status") in {"completed", "deferred"} for t in state.targets.values())
        return state
