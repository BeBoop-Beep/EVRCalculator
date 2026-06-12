from __future__ import annotations

import hashlib
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence

from backend.desirability.normalization import normalize_pokemon_name_key


logger = logging.getLogger(__name__)

SOURCE_NAME = "google_trends_search_interest"
QUERY_TYPE_SEARCH_TERM = "search_term"
DEFAULT_GEO = "US"
DEFAULT_ANCHOR_TERM = "Pikachu"
DEFAULT_BATCH_SIZE = 5


@dataclass(frozen=True)
class TrendTimeframe:
    timeframe: str
    window_role: str
    label: str


DEFAULT_TIMEFRAMES = (
    TrendTimeframe("today 1-m", "recent", "Recent Trend Score component"),
    TrendTimeframe("today 3-m", "validation", "Recent validation window"),
    TrendTimeframe("today 12-m", "current", "Search Popularity Score component"),
    TrendTimeframe("today 5-y", "baseline", "Long-term baseline component"),
)


AMBIGUOUS_QUERY_NAME_KEYS = {
    "persian",
    "onix",
    "golem",
    "ditto",
    "muk",
    "abra",
    "haunter",
    "jynx",
    "type null",
    "mr mime",
    "porygon z",
}

QUERY_TERM_OVERRIDES_BY_POKEDEX = {
    83: "Farfetch'd",
    122: "Mr. Mime",
    250: "Ho-Oh",
    474: "Porygon Z",
    439: "Mime Jr.",
    669: "Flabebe",
    772: "Type: Null",
    782: "Jangmo-o",
    783: "Hakamo-o",
    784: "Kommo-o",
    865: "Sirfetch'd",
    946: "Bramblin",
    947: "Brambleghast",
    1001: "Wo-Chien",
    1002: "Chien-Pao",
    1003: "Ting-Lu",
    1004: "Chi-Yu",
}


QUERY_TERM_OVERRIDE_RULES_BY_NAME_KEY = {
    "nidoran f": ("Nidoran", "gender descriptor removed for Google Trends species query"),
    "nidoran female": ("Nidoran", "gender descriptor removed for Google Trends species query"),
    "nidoran m": ("Nidoran", "gender descriptor removed for Google Trends species query"),
    "nidoran male": ("Nidoran", "gender descriptor removed for Google Trends species query"),
    "porygon z": ("Porygon Z", "punctuation normalized for Google Trends query matching"),
    "deoxys normal": ("Deoxys", "form descriptor removed for Google Trends species query"),
    "wormadam plant": ("Wormadam", "form descriptor removed for Google Trends species query"),
    "giratina altered": ("Giratina", "form descriptor removed for Google Trends species query"),
    "shaymin land": ("Shaymin", "form descriptor removed for Google Trends species query"),
    "basculin red striped": ("Basculin", "form descriptor removed for Google Trends species query"),
    "basculin red stripes": ("Basculin", "form descriptor removed for Google Trends species query"),
    "darmanitan standard": ("Darmanitan", "form descriptor removed for Google Trends species query"),
    "tornadus incarnate": ("Tornadus", "form descriptor removed for Google Trends species query"),
    "thundurus incarnate": ("Thundurus", "form descriptor removed for Google Trends species query"),
    "landorus incarnate": ("Landorus", "form descriptor removed for Google Trends species query"),
    "meowstic male": ("Meowstic", "gender descriptor removed for Google Trends species query"),
    "meowstic female": ("Meowstic", "gender descriptor removed for Google Trends species query"),
    "aegislash shield": ("Aegislash", "form descriptor removed for Google Trends species query"),
    "minior red meteor": ("Minior", "form descriptor removed for Google Trends species query"),
    "mimikyu disguised": ("Mimikyu", "state descriptor removed for Google Trends species query"),
    "mimikyu disguise": ("Mimikyu", "state descriptor removed for Google Trends species query"),
    "toxtricity amped": ("Toxtricity", "form descriptor removed for Google Trends species query"),
    "toxtricity low key": ("Toxtricity", "form descriptor removed for Google Trends species query"),
    "urshifu single strike": ("Urshifu", "form descriptor removed for Google Trends species query"),
    "urshifu rapid strike": ("Urshifu", "form descriptor removed for Google Trends species query"),
    "maushold family of four": ("Maushold", "form descriptor removed for Google Trends species query"),
    "maushold family of three": ("Maushold", "form descriptor removed for Google Trends species query"),
    "squawkabilly green plumage": ("Squawkabilly", "form descriptor removed for Google Trends species query"),
    "squawkabilly blue plumage": ("Squawkabilly", "form descriptor removed for Google Trends species query"),
    "squawkabilly yellow plumage": ("Squawkabilly", "form descriptor removed for Google Trends species query"),
    "squawkabilly white plumage": ("Squawkabilly", "form descriptor removed for Google Trends species query"),
    "palafin zero": ("Palafin", "state descriptor removed for Google Trends species query"),
    "palafin hero": ("Palafin", "state descriptor removed for Google Trends species query"),
    "tatsugiri curly": ("Tatsugiri", "form descriptor removed for Google Trends species query"),
    "tatsugiri droopy": ("Tatsugiri", "form descriptor removed for Google Trends species query"),
    "tatsugiri stretchy": ("Tatsugiri", "form descriptor removed for Google Trends species query"),
    "dudunsparce two segment": ("Dudunsparce", "form descriptor removed for Google Trends species query"),
    "dudunsparce three segment": ("Dudunsparce", "form descriptor removed for Google Trends species query"),
}


@dataclass(frozen=True)
class TrendPokemon:
    pokemon_reference_id: Any
    pokedex_number: Optional[int]
    pokemon_name: str
    query_term: str
    original_query_term: str
    query_term_override_reason: Optional[str]
    is_ambiguous: bool


@dataclass(frozen=True)
class TrendBatch:
    batch_key: str
    anchor_term: str
    pokemon: List[TrendPokemon]

    @property
    def terms(self) -> List[str]:
        seen: set[str] = set()
        terms: List[str] = []
        for term in [self.anchor_term, *[item.query_term for item in self.pokemon]]:
            if term.casefold() in seen:
                continue
            seen.add(term.casefold())
            terms.append(term)
        return terms


@dataclass
class TrendProviderResponse:
    status: str
    interest_by_term: Dict[str, float] = field(default_factory=dict)
    raw_payload: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    retryable: bool = False
    error_type: Optional[str] = None


class GoogleTrendsProvider(Protocol):
    provider_name: str

    def fetch_interest(
        self,
        *,
        terms: Sequence[str],
        timeframe: str,
        geo: str,
        query_type: str,
    ) -> TrendProviderResponse:
        ...


class ProviderUnavailableError(RuntimeError):
    pass


class PytrendsGoogleTrendsProvider:
    provider_name = "pytrends"

    def __init__(self, *, hl: str = "en-US", tz: int = 360, timeout: tuple[int, int] = (10, 30)):
        try:
            from pytrends.request import TrendReq
        except ImportError as exc:
            raise ProviderUnavailableError(
                "pytrends is not installed. Install backend requirements or use --provider fixture for dry-run diagnostics."
            ) from exc

        self.client = TrendReq(hl=hl, tz=tz, timeout=timeout)

    def fetch_interest(
        self,
        *,
        terms: Sequence[str],
        timeframe: str,
        geo: str,
        query_type: str,
    ) -> TrendProviderResponse:
        if query_type != QUERY_TYPE_SEARCH_TERM:
            return TrendProviderResponse(
                status="failed",
                error=f"Unsupported query_type={query_type}; only search_term is implemented.",
                retryable=False,
            )

        try:
            self.client.build_payload(list(terms), cat=0, timeframe=timeframe, geo=geo, gprop="")
            frame = self.client.interest_over_time()
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if _looks_rate_limited(error):
                return TrendProviderResponse(
                    status="rate_limited",
                    error=error,
                    retryable=True,
                    error_type="rate_limited_429",
                )
            retryable = _looks_retryable(error)
            return TrendProviderResponse(
                status="failed",
                error=error,
                retryable=retryable,
                error_type="retryable_provider_error" if retryable else "provider_error",
            )

        if frame is None or frame.empty:
            return TrendProviderResponse(
                status="insufficient_data",
                raw_payload={"terms": list(terms), "timeframe": timeframe, "geo": geo, "rows": []},
            )

        if "isPartial" in frame.columns:
            frame = frame.drop(columns=["isPartial"])

        means = {term: round(float(frame[term].mean()), 6) for term in terms if term in frame.columns}
        sample_points = []
        for timestamp, row in frame.tail(12).iterrows():
            sample_points.append(
                {
                    "date": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
                    "values": {term: _safe_float(row.get(term)) for term in terms if term in frame.columns},
                }
            )

        return TrendProviderResponse(
            status="captured",
            interest_by_term=means,
            raw_payload={
                "terms": list(terms),
                "timeframe": timeframe,
                "geo": geo,
                "query_type": query_type,
                "aggregation": "mean_interest_over_time",
                "sample_points_tail": sample_points,
            },
        )


class FixtureGoogleTrendsProvider:
    """Deterministic dry-run provider for validating ingestion flow without external Trends access."""

    provider_name = "fixture_diagnostic"

    _timeframe_multiplier = {
        "today 1-m": 1.15,
        "today 3-m": 1.05,
        "today 12-m": 1.0,
        "today 5-y": 0.9,
    }

    def fetch_interest(
        self,
        *,
        terms: Sequence[str],
        timeframe: str,
        geo: str,
        query_type: str,
    ) -> TrendProviderResponse:
        values: Dict[str, float] = {}
        for term in terms:
            base = _deterministic_interest(term)
            multiplier = self._timeframe_multiplier.get(timeframe, 1.0)
            values[term] = round(max(0.0, min(100.0, base * multiplier)), 6)
        if DEFAULT_ANCHOR_TERM in terms:
            values[DEFAULT_ANCHOR_TERM] = max(values.get(DEFAULT_ANCHOR_TERM, 0.0), 75.0)
        return TrendProviderResponse(
            status="captured",
            interest_by_term=values,
            raw_payload={
                "provider_note": "Fixture diagnostic values; not live Google Trends data.",
                "terms": list(terms),
                "timeframe": timeframe,
                "geo": geo,
                "query_type": query_type,
                "aggregation": "deterministic_fixture",
            },
        )


class UnavailableGoogleTrendsProvider:
    provider_name = "unavailable"

    def __init__(self, reason: str):
        self.reason = reason

    def fetch_interest(
        self,
        *,
        terms: Sequence[str],
        timeframe: str,
        geo: str,
        query_type: str,
    ) -> TrendProviderResponse:
        return TrendProviderResponse(status="failed", error=self.reason, retryable=False)


def make_provider(provider_name: str, *, dry_run: bool) -> GoogleTrendsProvider:
    normalized = provider_name.strip().casefold()
    if normalized == "fixture":
        return FixtureGoogleTrendsProvider()
    if normalized == "pytrends":
        return PytrendsGoogleTrendsProvider()
    if normalized != "auto":
        raise ValueError(f"Unsupported provider: {provider_name}")

    try:
        return PytrendsGoogleTrendsProvider()
    except ProviderUnavailableError as exc:
        if dry_run:
            logger.warning("Falling back to fixture diagnostic provider for dry-run: %s", exc)
            return FixtureGoogleTrendsProvider()
        return UnavailableGoogleTrendsProvider(str(exc))


def build_trend_pokemon(reference: Dict[str, Any]) -> TrendPokemon:
    pokedex_number = _as_int(reference.get("pokedex_number"))
    query_metadata = pokemon_query_term_metadata(reference)
    return TrendPokemon(
        pokemon_reference_id=reference.get("id"),
        pokedex_number=pokedex_number,
        pokemon_name=str(reference.get("display_name") or reference.get("canonical_name") or query_metadata["query_term"]),
        query_term=query_metadata["query_term"],
        original_query_term=query_metadata["original_query_term"],
        query_term_override_reason=query_metadata["override_reason"],
        is_ambiguous=is_ambiguous_query_term(query_metadata["query_term"]),
    )


def pokemon_query_term(reference: Dict[str, Any]) -> str:
    return pokemon_query_term_metadata(reference)["query_term"]


def pokemon_query_term_metadata(reference: Dict[str, Any]) -> Dict[str, Optional[str]]:
    pokedex_number = _as_int(reference.get("pokedex_number"))
    original_query_term = _default_query_term(reference)
    override = _query_term_name_override(reference, original_query_term)
    if override is not None:
        return {
            "query_term": override[0],
            "original_query_term": original_query_term,
            "override_reason": override[1],
        }
    if pokedex_number in QUERY_TERM_OVERRIDES_BY_POKEDEX:
        query_term = QUERY_TERM_OVERRIDES_BY_POKEDEX[pokedex_number]
        reason = "explicit Pokedex query-term spelling override"
        if query_term == original_query_term:
            reason = None
        return {
            "query_term": query_term,
            "original_query_term": original_query_term,
            "override_reason": reason,
        }
    return {
        "query_term": original_query_term,
        "original_query_term": original_query_term,
        "override_reason": None,
    }


def _default_query_term(reference: Dict[str, Any]) -> str:
    display_name = str(reference.get("display_name") or "").strip()
    if display_name:
        return display_name
    canonical_name = str(reference.get("canonical_name") or "").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in canonical_name.split())


def _query_term_name_override(
    reference: Dict[str, Any],
    original_query_term: str,
) -> Optional[tuple[str, str]]:
    candidate_names = [
        original_query_term,
        str(reference.get("display_name") or "").strip(),
        str(reference.get("canonical_name") or "").replace("-", " ").strip(),
    ]
    for candidate in candidate_names:
        key = normalize_pokemon_name_key(candidate)
        if key in QUERY_TERM_OVERRIDE_RULES_BY_NAME_KEY:
            return QUERY_TERM_OVERRIDE_RULES_BY_NAME_KEY[key]
    return None


def is_ambiguous_query_term(query_term: str) -> bool:
    return normalize_pokemon_name_key(query_term) in AMBIGUOUS_QUERY_NAME_KEYS


def build_anchor_batches(
    references: Iterable[Dict[str, Any]],
    *,
    anchor_term: str = DEFAULT_ANCHOR_TERM,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> List[TrendBatch]:
    if batch_size < 2 or batch_size > 5:
        raise ValueError("Google Trends batching supports an anchor plus 1-4 Pokemon terms; batch_size must be 2-5.")

    pokemon = [build_trend_pokemon(reference) for reference in references]
    non_anchor = [item for item in pokemon if item.query_term.casefold() != anchor_term.casefold()]
    terms_per_batch = batch_size - 1
    batches: List[TrendBatch] = []

    for start in range(0, len(non_anchor), terms_per_batch):
        chunk = non_anchor[start : start + terms_per_batch]
        batch_terms = "|".join(item.query_term for item in chunk)
        batch_hash = hashlib.sha1(f"{anchor_term}|{batch_terms}".encode("utf-8")).hexdigest()[:12]
        batches.append(TrendBatch(batch_key=f"{anchor_term.casefold()}_{batch_hash}", anchor_term=anchor_term, pokemon=chunk))

    if not batches and pokemon:
        batch_hash = hashlib.sha1(anchor_term.encode("utf-8")).hexdigest()[:12]
        batches.append(TrendBatch(batch_key=f"{anchor_term.casefold()}_{batch_hash}", anchor_term=anchor_term, pokemon=[]))

    return batches


def fetch_timeframe_rows(
    *,
    provider: GoogleTrendsProvider,
    references: List[Dict[str, Any]],
    timeframe: TrendTimeframe,
    geo: str,
    query_type: str,
    anchor_term: str,
    batch_size: int,
    delay_seconds: float,
    max_retries: int,
    retry_backoff_seconds: float,
    stop_after_consecutive_429s: int = 3,
    cooldown_after_429_seconds: float = 900.0,
) -> Dict[str, Any]:
    batches = build_anchor_batches(references, anchor_term=anchor_term, batch_size=batch_size)
    rows: List[Dict[str, Any]] = []
    batch_reports: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    consecutive_429s = 0
    rate_limited_batches = 0
    stopped_early = False
    anchor_row_added = False
    trend_pokemon = [build_trend_pokemon(reference) for reference in references]
    anchor_pokemon = next((item for item in trend_pokemon if item.query_term.casefold() == anchor_term.casefold()), None)

    for index, batch in enumerate(batches, start=1):
        response = _fetch_with_retries(
            provider=provider,
            terms=batch.terms,
            timeframe=timeframe.timeframe,
            geo=geo,
            query_type=query_type,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
        batch_report = {
            "batch_key": batch.batch_key,
            "terms": batch.terms,
            "status": response.status,
            "error": response.error,
            "error_type": response.error_type,
        }
        batch_reports.append(batch_report)

        if response.status != "captured":
            failures.append(batch_report)
            if response.status == "rate_limited" or response.error_type == "rate_limited_429":
                consecutive_429s += 1
                rate_limited_batches += 1
                logger.warning(
                    "Google Trends rate limit for batch %s (%s consecutive 429-style failure(s), threshold=%s).",
                    batch.batch_key,
                    consecutive_429s,
                    stop_after_consecutive_429s,
                )
                if stop_after_consecutive_429s > 0 and consecutive_429s >= stop_after_consecutive_429s:
                    stopped_early = True
                    logger.warning(
                        "Stopping Google Trends timeframe=%s after %s consecutive 429-style failure(s).",
                        timeframe.timeframe,
                        consecutive_429s,
                    )
                    break
                if cooldown_after_429_seconds > 0 and index < len(batches):
                    logger.warning("Cooling down %.1fs after Google Trends 429-style failure.", cooldown_after_429_seconds)
                    time.sleep(cooldown_after_429_seconds)
            else:
                consecutive_429s = 0
        else:
            consecutive_429s = 0
            anchor_value = _safe_float(response.interest_by_term.get(anchor_term))
            if anchor_pokemon is not None and not anchor_row_added:
                rows.append(
                    _source_row(
                        pokemon=anchor_pokemon,
                        timeframe=timeframe,
                        geo=geo,
                        query_type=query_type,
                        anchor_term=anchor_term,
                        batch=batch,
                        raw_interest_value=anchor_value,
                        anchor_interest_value=anchor_value,
                        raw_payload=response.raw_payload,
                    )
                )
                anchor_row_added = True

            for pokemon in batch.pokemon:
                raw_value = _safe_float(response.interest_by_term.get(pokemon.query_term))
                rows.append(
                    _source_row(
                        pokemon=pokemon,
                        timeframe=timeframe,
                        geo=geo,
                        query_type=query_type,
                        anchor_term=anchor_term,
                        batch=batch,
                        raw_interest_value=raw_value,
                        anchor_interest_value=anchor_value,
                        raw_payload=response.raw_payload,
                    )
                )

        if delay_seconds > 0 and index < len(batches):
            time.sleep(delay_seconds)

    return {
        "timeframe": timeframe.timeframe,
        "window_role": timeframe.window_role,
        "label": timeframe.label,
        "rows": rows,
        "batches_planned": len(batches),
        "batches_attempted": len(batch_reports),
        "batches_succeeded": sum(1 for report in batch_reports if report["status"] == "captured"),
        "batches_failed": len(failures),
        "rate_limited_batches": rate_limited_batches,
        "stopped_early": stopped_early,
        "stop_reason": "rate_limited_gracefully" if stopped_early else None,
        "failed_query_sample": failures[:10],
        "batch_reports": batch_reports,
    }


def _fetch_with_retries(
    *,
    provider: GoogleTrendsProvider,
    terms: Sequence[str],
    timeframe: str,
    geo: str,
    query_type: str,
    max_retries: int,
    retry_backoff_seconds: float,
) -> TrendProviderResponse:
    attempts = max(1, max_retries + 1)
    last_response: Optional[TrendProviderResponse] = None
    for attempt in range(1, attempts + 1):
        response = provider.fetch_interest(terms=terms, timeframe=timeframe, geo=geo, query_type=query_type)
        if response.status == "captured" or not response.retryable or attempt >= attempts:
            return response
        last_response = response
        sleep_seconds = retry_backoff_seconds * math.pow(2, attempt - 1)
        if response.status == "rate_limited" or response.error_type == "rate_limited_429":
            logger.warning(
                "Google Trends batch attempt %s/%s hit a 429/rate limit: %s; sleeping %.1fs",
                attempt,
                attempts,
                response.error,
                sleep_seconds,
            )
        else:
            logger.warning(
                "Google Trends batch attempt %s/%s failed with retryable error: %s; sleeping %.1fs",
                attempt,
                attempts,
                response.error,
                sleep_seconds,
            )
        time.sleep(sleep_seconds)
    return last_response or TrendProviderResponse(status="failed", error="Unknown provider failure", retryable=False)


def _source_row(
    *,
    pokemon: TrendPokemon,
    timeframe: TrendTimeframe,
    geo: str,
    query_type: str,
    anchor_term: str,
    batch: TrendBatch,
    raw_interest_value: Optional[float],
    anchor_interest_value: Optional[float],
    raw_payload: Dict[str, Any],
) -> Dict[str, Any]:
    relative_to_anchor: Optional[float] = None
    if raw_interest_value is not None and anchor_interest_value is not None and anchor_interest_value > 0:
        relative_to_anchor = round(raw_interest_value / anchor_interest_value, 8)

    confidence = "high"
    if raw_interest_value is None or anchor_interest_value is None or anchor_interest_value <= 0:
        confidence = "insufficient"
    elif raw_interest_value <= 0:
        confidence = "low"
    elif pokemon.is_ambiguous:
        confidence = "low"
    elif raw_interest_value < 1 or anchor_interest_value < 1:
        confidence = "medium"

    return {
        "snapshot_id": None,
        "source_name": SOURCE_NAME,
        "pokemon_reference_id": pokemon.pokemon_reference_id,
        "pokedex_number": pokemon.pokedex_number,
        "pokemon_name": pokemon.pokemon_name,
        "query_term": pokemon.query_term,
        "geo": geo,
        "timeframe": timeframe.timeframe,
        "window_role": timeframe.window_role,
        "query_type": query_type,
        "anchor_term": anchor_term,
        "batch_key": batch.batch_key,
        "raw_interest_value": raw_interest_value,
        "anchor_interest_value": anchor_interest_value,
        "relative_to_anchor": relative_to_anchor,
        "is_ambiguous": pokemon.is_ambiguous,
        "extraction_confidence": confidence,
        "raw_row_json": {
            "terms": batch.terms,
            "query_term_audit": {
                "original_query_term": pokemon.original_query_term,
                "corrected_query_term": pokemon.query_term,
                "override_applied": pokemon.query_term != pokemon.original_query_term,
                "override_reason": pokemon.query_term_override_reason,
            },
            "provider_payload": raw_payload,
            "measurement_note": "Google Trends values are normalized relative search interest, not absolute search volume.",
        },
    }


def _looks_retryable(error: str) -> bool:
    lowered = error.casefold()
    return any(token in lowered for token in ("429", "rate", "timeout", "temporarily", "connection", "reset"))


def _looks_rate_limited(error: str) -> bool:
    lowered = error.casefold()
    return "429" in lowered or "toomanyrequest" in lowered or "too many request" in lowered


def _deterministic_interest(term: str) -> float:
    digest = hashlib.sha1(term.casefold().encode("utf-8")).hexdigest()
    value = int(digest[:8], 16) % 90
    boosted = {
        "pikachu": 95,
        "charizard": 88,
        "eevee": 80,
        "mewtwo": 78,
        "gengar": 72,
    }.get(term.casefold())
    return float(boosted if boosted is not None else 5 + value)


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
