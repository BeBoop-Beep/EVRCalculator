"""Explorer Focused Market Activity V1 -- pure, versioned domain rules (FMA-0).

This module is the executable half of
``docs/research/market_activity_v1/CONTRACT.md``. It is deliberately pure:

* it imports only the Python standard library (an allowlist test enforces it);
* it never constructs database, HTTP or provider clients and never opens a
  socket (a provider-egress tripwire test enforces it);
* it never mutates, rewrites or reinterprets stored evidence. Legacy rows are
  *evaluated* under the stricter V1 rules and the disagreement is reported,
  never written back.

Scope boundary: read-only activity facts for /Market/Explorer only. Nothing
here is a price authority, Set Value input, Market Index input, RIP input,
Collector Appeal input, Fair Value fit, population source, or condition-to-NM
conversion. There are no buy/sell signals, no OHLC, no demand/scarcity
composite and no sales inferred from disappearing listings.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Versions. Any semantic change to a rule below requires a version bump; the
# fixture manifest fingerprints these strings.
# ---------------------------------------------------------------------------
#
# FMA-0.1 (review closure) bumps: contract 1.1, domain 1.1.0, window readiness
# v2 (typed/bound/non-future proof), supply provenance v2 (current-qualified
# offers, unknown pagination, capability expiry), membership v2 (independent
# activity-generation pin, roster ref, opaque cursor, rank integrity), and the
# new observation, series, peer-population and cursor rule versions.
CONTRACT_VERSION = "market_activity_v1.1"
DOMAIN_VERSION = "market_activity_domain_v1.1.0"
IDENTITY_RULES_VERSION = "fma_exact_identity_v1"
GRADING_RULES_VERSION = "fma_grading_identity_v1"
OBSERVATION_RULES_VERSION = "fma_sold_observation_v1"
WINDOW_READINESS_VERSION = "fma_window_readiness_v2"
SUPPLY_PROVENANCE_VERSION = "fma_supply_provenance_v2"
SERIES_VERSION = "fma_activity_series_v1"
TIE_POLICY_VERSION = "midrank_v1"
PEER_POPULATION_VERSION = "fma_peer_population_v2"
MEMBERSHIP_CONTRACT_VERSION = "fma_membership_v2"
CURSOR_VERSION = "fma_cursor_v1"

MEMBERSHIP_MODE = "CURRENT_ROSTER_RETROSPECTIVE"
MEMBERSHIP_LABEL = "Activity for current constituents"
PERCENTILE_LABEL = "Activity percentile"

WINDOW_DAYS = (7, 30, 90, 180)
SUPPORTED_ASSETS = ("cards",)
SOLD_SOURCE = "pkmnprices_ebay_sold"
ASK_SOURCE = "pkmnprices_tcgplayer_listings"
SUPPORTED_CURRENCY = "USD"
SOLD_CONDITION_BASIS = "UNKNOWN_CONDITION"  # sold rows carry no raw condition
ASK_CONDITION_BASIS = "NEAR_MINT_LISTED"

# The only population the V1 peer badge may name. It is a modern (Scarlet and
# Violet + Mega Evolution), price-band-balanced research panel -- never "all
# Pokemon".
RESEARCH_PANEL_ID = "market_microstructure_core_panel_v1"
RESEARCH_PANEL_SCOPE_LABEL = "Core Panel V1 research panel (modern, price-balanced)"

# ---------------------------------------------------------------------------
# Named display/operations policy. These are configurable product thresholds,
# NOT scientific claims about liquidity or market completeness.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DisplayPolicy:
    version: str = "fma_display_policy_v1"
    ask_confirmation_max_age_hours: int = 24
    sold_head_receipt_max_age_hours: int = 36
    price_summary_min_records: int = 5
    percentile_min_other_peers: int = 30
    future_timestamp_skew_seconds: int = 300

    def as_contract(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "askConfirmationMaxAgeHours": self.ask_confirmation_max_age_hours,
            "soldHeadReceiptMaxAgeHours": self.sold_head_receipt_max_age_hours,
            "priceSummaryMinRecords": self.price_summary_min_records,
            "percentileMinOtherPeers": self.percentile_min_other_peers,
            "futureTimestampSkewSeconds": self.future_timestamp_skew_seconds,
            "tiePolicy": TIE_POLICY_VERSION,
        }


DEFAULT_POLICY = DisplayPolicy()

# ---------------------------------------------------------------------------
# Deterministic reason codes. Order here is the canonical emission order; every
# emitted list is sorted by this order and de-duplicated. The JSON schema enum
# is kept in sync by a test.
# ---------------------------------------------------------------------------
REASON_CODES: tuple[str, ...] = (
    # request / scope
    "UNSUPPORTED_ASSET",
    "GENERATION_MISMATCH",
    "ACTIVITY_GENERATION_MISMATCH",
    "ACTIVITY_GENERATION_EXPIRED",
    "ROSTER_REVISION_UNSTABLE",
    "QUERY_FINGERPRINT_IS_NOT_A_REVISION",
    "ROSTER_REVISION_MISMATCH",
    "ROSTER_INTEGRITY_VIOLATION",
    "CURSOR_INVALID",
    "CURSOR_MISMATCH",
    "INSTRUMENT_NOT_IN_ROSTER",
    "INVALID_INSTRUMENT_KEY",
    # identity
    "ATTRIBUTION_MISSING",
    "ATTRIBUTION_SHARED",
    "ATTRIBUTION_UNKNOWN",
    "PROVIDER_VARIANT_MISSING",
    "PROVIDER_VARIANT_UNPARSED_TOKENS",
    "CANDIDATE_SET_INCOMPLETE",
    "IDENTITY_EDITION_UNPROVEN",
    "IDENTITY_PRINTING_UNPROVEN",
    "IDENTITY_SPECIAL_TYPE_UNSUPPORTED",
    "IDENTITY_NO_MATCH",
    "IDENTITY_AMBIGUOUS",
    "CURRENCY_UNSUPPORTED",
    # grading
    "GRADING_INCOMPLETE",
    "GRADER_UNRECOGNIZED",
    "GRADE_UNRECOGNIZED",
    "QUALIFIER_UNRECOGNIZED",
    "TIER_MISMATCH",
    # evidence integrity
    "EVIDENCE_DUPLICATE",
    "EVIDENCE_CONFLICT",
    "INVALID_EVIDENCE_ROW",
    # window readiness
    "NOT_COLLECTED",
    "COMPLETENESS_RECEIPT_MISSING",
    "SYNC_STATUS_NOT_PROOF",
    "WALK_RECEIPT_MALFORMED",
    "WALK_PAGINATION_UNKNOWN",
    "WALK_BINDING_MISMATCH",
    "WALK_SORT_NOT_DATE_DESC",
    "WALK_HEAD_UNKNOWN",
    "WALK_CURSOR_CHAIN_BROKEN",
    "WALK_FILTER_UNSTABLE",
    "WALK_NOT_DATE_DESCENDING",
    "STREAM_DOES_NOT_COVER_TIER",
    "COMBINED_STREAM_SEMANTICS_UNPROVEN",
    "LOWER_BOUNDARY_NOT_REACHED",
    "BOUNDARY_DATE_PARTIALLY_FETCHED",
    "RIGHT_EDGE_UNRECONCILED",
    "RIGHT_EDGE_INVALID",
    "RIGHT_EDGE_IN_FUTURE",
    "RIGHT_EDGE_BINDING_MISMATCH",
    "RIGHT_EDGE_DAY_OPEN",
    "RIGHT_EDGE_STALE",
    "LATE_INGESTION_AFTER_RECONCILIATION",
    "CHECKPOINT_PAGES_PENDING",
    "SAME_INGESTION_TIMESTAMP_UNDRAINED",
    # supply
    "SUPPLY_COLLECTION_FAILED",
    "SOURCE_CONFIRMATION_MISSING",
    "SOURCE_CONFIRMATION_IN_FUTURE",
    "SOURCE_CONFIRMATION_MIXED",
    "SOURCE_CONFIRMATION_REPEATED",
    "UNCONFIRMED_OFFERS_EXCLUDED",
    "ASKS_STALE",
    "EMPTY_WITHOUT_SOURCE_FRESHNESS",
    "SUPPLY_PAGINATION_UNKNOWN",
    "SUPPLY_PAGINATION_CONTRADICTORY",
    "DEPTH_TRUNCATED",
    "SHIPPING_UNKNOWN",
    "SHIPPING_LEGACY_UNVERIFIED",
    "QUANTITY_DEFAULTED",
    "QUANTITY_LEGACY_UNVERIFIED",
    # metrics / peers
    "THIN_RECORDS",
    "NO_RECORDS",
    "NO_PEERS",
    "INSUFFICIENT_PEERS",
    "ALL_ZERO",
    "ALL_PEERS_TIED",
    "ZERO_BASELINE",
    "BASELINE_MISSING",
    "WINDOW_NOT_PROVEN",
    "FEATURE_DISABLED_V1",
)
_REASON_ORDER = {code: index for index, code in enumerate(REASON_CODES)}


def reasons(*codes: Iterable[str] | str) -> list[str]:
    """Deterministic, de-duplicated, registry-validated reason list."""
    flat: list[str] = []
    for item in codes:
        if isinstance(item, str):
            flat.append(item)
        else:
            flat.extend(item)
    unknown = [code for code in flat if code not in _REASON_ORDER]
    if unknown:
        raise ValueError(f"unregistered reason code(s): {sorted(set(unknown))}")
    return sorted(set(flat), key=_REASON_ORDER.__getitem__)


# ---------------------------------------------------------------------------
# Small pure helpers (timestamps, money, hashing).
# ---------------------------------------------------------------------------
_TZ_SHORT = re.compile(r"([+-]\d{2})$")
_FRACTION = re.compile(r"\.(\d+)")


def parse_timestamp(value: Any) -> datetime | None:
    """Parse ISO-8601/Postgres timestamps to aware UTC; None for empty.

    Accepts ``Z``, ``+00`` and variable fractional digits so behaviour does not
    depend on the Python minor version. Naive values are rejected: a timestamp
    without an offset cannot be compared against a freshness policy.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        text = text.replace(" ", "T", 1).replace("Z", "+00:00")
        text = _TZ_SHORT.sub(r"\1:00", text)
        text = _FRACTION.sub(lambda m: "." + (m.group(1) + "000000")[:6], text, count=1)
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp without offset: {value!r}")
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def money(value: Any) -> Decimal:
    """Exact non-negative cents. Never goes through float."""
    if isinstance(value, float):
        raise ValueError("money must not be a float")
    try:
        out = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid money: {value!r}") from exc
    if not out.is_finite() or out < 0 or out.as_tuple().exponent < -2:
        raise ValueError(f"invalid money: {value!r}")
    return out.quantize(Decimal("0.01"))


def money_json(value: Decimal | None, currency: str = SUPPORTED_CURRENCY) -> dict[str, str] | None:
    if value is None:
        return None
    return {"amount": str(value.quantize(Decimal("0.01"))), "currency": currency}


def pct_string(numerator: int, denominator: int) -> str:
    value = (Decimal(numerator) * Decimal(100) / Decimal(denominator))
    return str(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


# ---------------------------------------------------------------------------
# 1. Exact instrument keys.
# ---------------------------------------------------------------------------
KNOWN_GRADERS = ("ACE", "BGS", "CGC", "PSA", "SGC", "TAG")
_GRADE_PATTERN = re.compile(r"^(?:10|[1-9](?:\.5)?)$")
# Opaque qualifiers recognised as *distinct* certified tiers. A recognised
# qualifier never merges into the ordinary tier; an unrecognised one never
# becomes a certified tier at all.
QUALIFIER_REGISTRY_VERSION = "fma_qualifier_registry_v1"
KNOWN_QUALIFIERS: dict[str, tuple[str, ...]] = {
    "BGS": ("Black Label",),
    "CGC": ("Pristine", "Perfect"),
    "TAG": ("Pristine",),
}
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_KEY_SAFE = re.compile(r"[^A-Za-z0-9.]")


def _key_token(value: str) -> str:
    return _KEY_SAFE.sub(lambda m: "%%%02X" % ord(m.group(0)), value)


def _key_untoken(value: str) -> str:
    return re.sub(r"%([0-9A-F]{2})", lambda m: chr(int(m.group(1), 16)), value)


@dataclass(frozen=True)
class GradingIdentity:
    state: str  # RAW | GRADED | GRADED_QUALIFIED | INCOMPLETE | UNRECOGNIZED
    grader: str | None
    grade: str | None
    qualifier: str | None
    reasons: tuple[str, ...] = ()

    @property
    def certified_tier(self) -> bool:
        return self.state in {"RAW", "GRADED", "GRADED_QUALIFIED"}

    def as_contract(self) -> dict[str, Any]:
        return {"state": self.state, "grader": self.grader, "grade": self.grade,
                "qualifier": self.qualifier, "reasons": list(self.reasons)}


def classify_grading(grader: Any, grade: Any, qualifier: Any = None, *,
                     provider_graded_flag: bool | None = None) -> GradingIdentity:
    """Classify slab identity without ever falling back to raw.

    * No grader, grade or qualifier AND the provider did not flag the row as
      graded -> RAW.
    * Any partial slab evidence (or a graded flag with no slab fields) ->
      INCOMPLETE. It is excluded from raw AND from every graded tier.
    * Grades are opaque strings: "9.5" stays "9.5"; "10.0" is not "10".
    * An unknown grader, non-standard grade, or unregistered qualifier ->
      UNRECOGNIZED: preserved as an observed fact, never a certified tier.
    """
    g = str(grader or "").strip() or None
    gr = str(grade).strip() if grade is not None and str(grade).strip() else None
    q = str(qualifier or "").strip() or None
    if not (g or gr or q):
        if provider_graded_flag:
            return GradingIdentity("INCOMPLETE", None, None, None, ("GRADING_INCOMPLETE",))
        return GradingIdentity("RAW", None, None, None)
    if not g or not gr:
        return GradingIdentity("INCOMPLETE", g, gr, q, ("GRADING_INCOMPLETE",))
    grader_norm = g.upper()
    why: list[str] = []
    if grader_norm not in KNOWN_GRADERS:
        why.append("GRADER_UNRECOGNIZED")
    if not _GRADE_PATTERN.match(gr):
        why.append("GRADE_UNRECOGNIZED")
    if q is not None:
        known = {item.casefold(): item for item in KNOWN_QUALIFIERS.get(grader_norm, ())}
        if q.casefold() not in known:
            why.append("QUALIFIER_UNRECOGNIZED")
        else:
            q = known[q.casefold()]
    if why:
        return GradingIdentity("UNRECOGNIZED", grader_norm, gr, q, tuple(reasons(why)))
    return GradingIdentity("GRADED_QUALIFIED" if q else "GRADED", grader_norm, gr, q)


def instrument_key(card_variant_id: str, grading: GradingIdentity) -> str:
    """Exact instrument key. Only certified tiers have a key."""
    variant = str(card_variant_id or "").strip().lower()
    if not _UUID.match(variant):
        raise ValueError("card_variant_id must be a UUID")
    if not grading.certified_tier:
        raise ValueError(f"no instrument key for grading state {grading.state}")
    if grading.state == "RAW":
        return f"card:{variant}:raw"
    qualifier = _key_token(grading.qualifier) if grading.qualifier else "-"
    return f"card:{variant}:graded:{grading.grader}:{_key_token(grading.grade or '')}:{qualifier}"


def parse_instrument_key(key: str) -> dict[str, Any]:
    parts = str(key or "").split(":")
    if len(parts) == 3 and parts[0] == "card" and parts[2] == "raw" and _UUID.match(parts[1]):
        grading = GradingIdentity("RAW", None, None, None)
        return {"asset": "cards", "cardVariantId": parts[1], "stream": "RAW", "grading": grading}
    if len(parts) == 6 and parts[0] == "card" and parts[2] == "graded" and _UUID.match(parts[1]):
        qualifier = None if parts[5] == "-" else _key_untoken(parts[5])
        grading = classify_grading(parts[3], _key_untoken(parts[4]), qualifier)
        if not grading.certified_tier or grading.state == "RAW":
            raise ValueError("INVALID_INSTRUMENT_KEY")
        if instrument_key(parts[1], grading) != key:
            raise ValueError("INVALID_INSTRUMENT_KEY")
        return {"asset": "cards", "cardVariantId": parts[1], "stream": "GRADED", "grading": grading}
    raise ValueError("INVALID_INSTRUMENT_KEY")


def tier_key(grading: GradingIdentity) -> str:
    if grading.state == "RAW":
        return "RAW"
    return f"GRADED:{grading.grader}:{grading.grade}:{grading.qualifier or '-'}"


# ---------------------------------------------------------------------------
# 3. Exact identity (provider attribution + internal variant proof).
# ---------------------------------------------------------------------------
_EDITION_PATTERNS = (
    ("1st-edition", re.compile(r"\b(?:1st|first)\s*edition\b", re.I)),
    ("shadowless", re.compile(r"\bshadowless\b", re.I)),
    ("unlimited", re.compile(r"\bunlimited\b", re.I)),
)
# Non-Holo MUST be tested before Holo: "\bholo\b" matches inside "Non-Holo"
# because "-" is a word boundary. (Audit finding against pkmnprices_sold.py.)
_PRINTING_PATTERNS = (
    ("reverse-holo", re.compile(r"\breverse[\s-]*holo(?:foil)?\b", re.I)),
    ("non-holo", re.compile(r"\b(?:non[\s-]*holo(?:foil)?|normal)\b", re.I)),
    ("holo", re.compile(r"\bholo(?:foil)?\b", re.I)),
)


def parse_provider_variant_strict(value: Any) -> dict[str, Any]:
    text = str(value or "").strip()
    residual = text
    edition = None
    for name, pattern in _EDITION_PATTERNS:
        if pattern.search(residual):
            edition = name
            residual = pattern.sub(" ", residual)
            break
    printing = None
    for name, pattern in _PRINTING_PATTERNS:
        if pattern.search(residual):
            printing = name
            residual = pattern.sub(" ", residual)
            break
    leftover = [token for token in re.split(r"[\s/,()-]+", residual) if token]
    return {"raw": text or None, "edition": edition, "printingType": printing,
            "unparsedTokens": leftover}


def _norm_dim(value: Any) -> str | None:
    text = str(value or "").strip().casefold().replace("_", "-")
    return text or None


@dataclass(frozen=True)
class IdentityDecision:
    state: str  # EXACT | AMBIGUOUS | NO_MATCH | UNPROVEN
    card_variant_id: str | None
    reasons: tuple[str, ...]

    @property
    def publishable(self) -> bool:
        return self.state == "EXACT" and not self.reasons


def resolve_exact_identity(
    *, attribution: Any, provider_variant: Any, candidates: Sequence[Mapping[str, Any]],
    candidate_scope: str, currency: Any = SUPPORTED_CURRENCY,
) -> IdentityDecision:
    """Exact identity requires BOTH provider attribution and internal proof.

    ``candidates`` must be the FULL set of internal variants of the physical
    card (``candidate_scope == "FULL_CARD_VARIANT_SET"``). Resolving against a
    target-only list is the audited one-candidate EXACT shortcut and is never
    publishable. Every dimension that could distinguish variants must be
    stated by the provider; an unstated dimension is not proof by elimination.
    """
    why: list[str] = []
    attr = str(attribution).strip().casefold() if attribution is not None else ""
    if not attr:
        why.append("ATTRIBUTION_MISSING")
    elif attr == "shared":
        why.append("ATTRIBUTION_SHARED")
    elif attr != "exact":
        why.append("ATTRIBUTION_UNKNOWN")
    if str(currency or "").upper() != SUPPORTED_CURRENCY:
        why.append("CURRENCY_UNSUPPORTED")
    if candidate_scope != "FULL_CARD_VARIANT_SET":
        why.append("CANDIDATE_SET_INCOMPLETE")
    parsed = parse_provider_variant_strict(provider_variant)
    if parsed["raw"] is None:
        why.append("PROVIDER_VARIANT_MISSING")
    elif parsed["unparsedTokens"]:
        why.append("PROVIDER_VARIANT_UNPARSED_TOKENS")

    pool = [dict(row) for row in candidates if row.get("id")]
    if any(_norm_dim(row.get("specialType") or row.get("special_type")) for row in pool):
        why.append("IDENTITY_SPECIAL_TYPE_UNSUPPORTED")
    editions = {_norm_dim(row.get("edition")) for row in pool}
    printings = {_norm_dim(row.get("printingType") or row.get("printing_type")) for row in pool}

    matched = pool
    if parsed["edition"]:
        matched = [row for row in matched if _norm_dim(row.get("edition")) == parsed["edition"]]
    elif len(editions) > 1 or any(editions - {None}):
        # Edition varies across siblings, or the candidate carries an edition
        # the provider never stated: not proof by elimination.
        why.append("IDENTITY_EDITION_UNPROVEN")
    if parsed["printingType"]:
        matched = [row for row in matched
                   if _norm_dim(row.get("printingType") or row.get("printing_type")) == parsed["printingType"]]
    elif len(printings) > 1:
        why.append("IDENTITY_PRINTING_UNPROVEN")

    if not matched:
        return IdentityDecision("NO_MATCH", None, tuple(reasons(why, "IDENTITY_NO_MATCH")))
    if len(matched) > 1:
        return IdentityDecision("AMBIGUOUS", None, tuple(reasons(why, "IDENTITY_AMBIGUOUS")))
    variant_id = str(matched[0]["id"]).lower()
    if why:
        return IdentityDecision("UNPROVEN", variant_id, tuple(reasons(why)))
    return IdentityDecision("EXACT", variant_id, ())


def evaluate_legacy_sold_row(stored: Mapping[str, Any], *, candidates: Sequence[Mapping[str, Any]],
                             candidate_scope: str) -> dict[str, Any]:
    """Re-evaluate one stored sold row under V1 rules WITHOUT rewriting it.

    Returns both classifications side by side so an audit can count
    disagreements. The stored ``identity_state`` is never modified.
    """
    decision = resolve_exact_identity(
        attribution=stored.get("attribution"), provider_variant=stored.get("provider_variant"),
        candidates=candidates, candidate_scope=candidate_scope, currency=stored.get("currency"),
    )
    legacy_exact = (str(stored.get("identity_state") or "") == "EXACT"
                    and str(stored.get("attribution") or "") == "exact")
    return {
        "legacyIdentityState": stored.get("identity_state"),
        "legacyExactUsd": bool(legacy_exact and str(stored.get("currency") or "") == "USD"),
        "fmaIdentityState": decision.state,
        "fmaPublishable": decision.publishable,
        "fmaReasons": list(decision.reasons),
        "agrees": bool(legacy_exact and str(stored.get("currency") or "") == "USD") == decision.publishable,
        "rewritten": False,
    }


# ---------------------------------------------------------------------------
# Evidence de-duplication (duplicate vs conflicting provider rows).
# ---------------------------------------------------------------------------
def _nonempty_text(value: Any) -> bool:
    return value is not None and not isinstance(value, bool) and bool(str(value).strip())


def validate_sold_row(row: Any) -> bool:
    """A sold row is structurally valid before it may take part in dedupe.

    Requires a listing identity (providerCardId + listingId), exact money, a
    parseable sold date and, when present, parseable offset-aware ingestion and
    collection timestamps. Invalid rows are quarantined as
    INVALID_EVIDENCE_ROW *before* deduplication, so a malformed copy can
    neither raise nor collapse into (or conflict with) a valid listing.
    """
    if not isinstance(row, Mapping):
        return False
    if not (_nonempty_text(row.get("providerCardId")) and _nonempty_text(row.get("listingId"))):
        return False
    try:
        money(row.get("price"))
        if row.get("soldAt") is None or isinstance(row.get("soldAt"), bool):
            return False
        parse_date(row.get("soldAt"))
        parse_timestamp(row.get("ingestedAt"))
        parse_timestamp(row.get("collectedAt"))
    except (ValueError, TypeError):
        return False
    return True


def dedupe_sold_records(records: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Keep one row per (source, providerCardId, listingId).

    Structurally invalid rows are quarantined first (INVALID_EVIDENCE_ROW).
    Identical economic facts (price, currency, soldAt) are duplicates: the
    first-seen row (earliest collectedAt, then input order) is kept. Rows that
    share a listing identity but disagree on those facts are a CONFLICT and
    every copy is excluded -- neither version is silently preferred.
    """
    groups: dict[tuple[str, str, str], list[tuple[int, dict[str, Any]]]] = {}
    excluded = {"INVALID_EVIDENCE_ROW": 0, "EVIDENCE_DUPLICATE": 0, "EVIDENCE_CONFLICT": 0}
    for index, row in enumerate(records):
        if not validate_sold_row(row):
            excluded["INVALID_EVIDENCE_ROW"] += 1
            continue
        key = (str(row.get("source") or SOLD_SOURCE), str(row.get("providerCardId")).strip(),
               str(row.get("listingId")).strip())
        groups.setdefault(key, []).append((index, dict(row)))
    kept: list[tuple[int, dict[str, Any]]] = []
    for items in groups.values():
        facts = {(str(money(r.get("price"))), str(r.get("currency") or "").upper(), parse_date(r.get("soldAt")))
                 for _, r in items}
        if len(facts) > 1:
            excluded["EVIDENCE_CONFLICT"] += len(items)
            continue
        # Earliest collection by parsed instant (never by string order), then
        # input order; a missing collectedAt sorts last.
        items.sort(key=lambda pair: (parse_timestamp(pair[1].get("collectedAt")) is None,
                                     parse_timestamp(pair[1].get("collectedAt"))
                                     or datetime.min.replace(tzinfo=timezone.utc), pair[0]))
        kept.append(items[0])
        excluded["EVIDENCE_DUPLICATE"] += len(items) - 1
    kept.sort(key=lambda pair: pair[0])
    return [row for _, row in kept], {k: excluded[k] for k in reasons([k for k, v in excluded.items() if v])}


# ---------------------------------------------------------------------------
# 4. Window readiness.
# ---------------------------------------------------------------------------
STREAMS = ("RAW_ONLY", "COMBINED", "GRADE_FILTERED")
READINESS_ORDER = {"PROVEN": 3, "PARTIAL": 2, "UNPROVEN": 1, "NOT_COLLECTED": 0}


def closed_window(as_of: Any, days: int) -> tuple[date, date]:
    """Closed [start, end] calendar-date window ending on ``as_of``."""
    if days not in WINDOW_DAYS:
        raise ValueError(f"window must be one of {WINDOW_DAYS}")
    end = parse_date(as_of)
    return end - timedelta(days=days - 1), end


def _is_count(value: Any) -> bool:
    """A non-negative integer that is not a bool (JSON true is not a count)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _typed_date(value: Any) -> date | None:
    """A 'YYYY-MM-DD' string (or date), else None. Never coerces other types."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()[:10]) if len(value.strip()) >= 10 else None
    except ValueError:
        return None


def _typed_timestamp(value: Any) -> datetime | None:
    try:
        return parse_timestamp(value) if isinstance(value, (str, datetime)) else None
    except ValueError:
        return None


def _page_type_reasons(pages: Sequence[Any], evaluated_date: date | None) -> list[str]:
    """Explicit, typed page fields. Unknown is never read as a default.

    * ``hasMore`` must be a real boolean; anything else is
      WALK_PAGINATION_UNKNOWN (unknown pagination is not exhaustion);
    * ``pageIndex`` equals the page position and ``rowCount`` is a
      non-negative integer;
    * ``hasMore is True`` requires a non-empty output cursor hash, ``hasMore is
      False`` requires none, and page 0 has no input cursor;
    * a page with rows has valid, ordered, non-future sold-date bounds; a
      zero-row page has no bounds and cannot claim more pages.
    """
    why: list[str] = []
    for index, page in enumerate(pages):
        if not isinstance(page, Mapping):
            why.append("WALK_RECEIPT_MALFORMED")
            continue
        has_more = page.get("hasMore")
        if not isinstance(has_more, bool):
            why.append("WALK_PAGINATION_UNKNOWN")
        position = page.get("pageIndex")
        if not _is_count(position) or position != index:
            why.append("WALK_RECEIPT_MALFORMED")
        row_count = page.get("rowCount")
        if not _is_count(row_count):
            why.append("WALK_RECEIPT_MALFORMED")
        out_cursor, in_cursor = page.get("outputCursorHash"), page.get("inputCursorHash")
        if has_more is True and not (isinstance(out_cursor, str) and out_cursor.strip()):
            why.append("WALK_RECEIPT_MALFORMED")
        if has_more is False and out_cursor is not None:
            why.append("WALK_RECEIPT_MALFORMED")
        if in_cursor is not None and not (isinstance(in_cursor, str) and in_cursor.strip()):
            why.append("WALK_RECEIPT_MALFORMED")
        hi_raw, lo_raw = page.get("maxSoldAt"), page.get("minSoldAt")
        if _is_count(row_count) and row_count > 0:
            hi, lo = _typed_date(hi_raw), _typed_date(lo_raw)
            if hi is None or lo is None or (evaluated_date is not None and hi > evaluated_date):
                why.append("WALK_RECEIPT_MALFORMED")
        elif row_count == 0:
            if hi_raw is not None or lo_raw is not None or has_more is True:
                why.append("WALK_RECEIPT_MALFORMED")
    return why


def _walk_structure_reasons(walk: Mapping[str, Any], evaluated_date: date | None = None) -> list[str]:
    why: list[str] = []
    if walk.get("sort") != "date_desc":
        why.append("WALK_SORT_NOT_DATE_DESC")
    raw_pages = walk.get("pages")
    if raw_pages is not None and not isinstance(raw_pages, (list, tuple)):
        return why + ["WALK_RECEIPT_MALFORMED"]
    pages = list(raw_pages or [])
    if not pages:
        return why + ["NOT_COLLECTED"]
    why.extend(_page_type_reasons(pages, evaluated_date))
    mapped = [page if isinstance(page, Mapping) else {} for page in pages]
    if mapped[0].get("inputCursorHash") is not None or walk.get("startedFromHead") is not True:
        why.append("WALK_HEAD_UNKNOWN")
    filters = {page.get("filterFingerprint") for page in mapped}
    if len(filters) != 1 or None in filters or walk.get("filterFingerprint") not in filters:
        why.append("WALK_FILTER_UNSTABLE")
    previous_min: date | None = None
    for index, page in enumerate(mapped):
        if index > 0:
            prior = mapped[index - 1]
            if (page.get("inputCursorHash") is None
                    or page.get("inputCursorHash") != prior.get("outputCursorHash")
                    or prior.get("hasMore") is not True):
                why.append("WALK_CURSOR_CHAIN_BROKEN")
        hi, lo = _typed_date(page.get("maxSoldAt")), _typed_date(page.get("minSoldAt"))
        if _is_count(page.get("rowCount")) and page["rowCount"] > 0 and hi is not None and lo is not None:
            if lo > hi or (previous_min is not None and hi > previous_min):
                why.append("WALK_NOT_DATE_DESCENDING")
            previous_min = lo
    return why


def _walk_binding_reasons(walk: Mapping[str, Any], provider_card_id: Any) -> list[str]:
    """A receipt proves nothing unless it is bound to THIS provider card and to
    a committed collection context (walkId + collectionRunId, committed)."""
    why: list[str] = []
    expected = str(provider_card_id).strip() if _nonempty_text(provider_card_id) else None
    actual = str(walk.get("providerCardId")).strip() if _nonempty_text(walk.get("providerCardId")) else None
    if expected is None or actual is None or expected != actual or walk.get("committed") is not True:
        why.append("WALK_BINDING_MISMATCH")
    if not (_nonempty_text(walk.get("walkId")) and _nonempty_text(walk.get("collectionRunId"))):
        why.append("WALK_RECEIPT_MALFORMED")
    return why


_RIGHT_EDGE_BINDING = (("providerCardId", "providerCardId"), ("stream", "stream"),
                       ("filterFingerprint", "filterFingerprint"), ("graderFilter", "graderFilter"),
                       ("gradeFilter", "gradeFilter"), ("headWalkId", "walkId"),
                       ("collectionRunId", "collectionRunId"))


def _right_edge(walk: Mapping[str, Any], evaluated_at: datetime,
                policy: DisplayPolicy) -> tuple[datetime | None, list[str]]:
    """Validated right-edge reconciliation, or (None, reasons).

    ``completed`` must be literally true, ``reconciledThrough`` a valid
    offset-aware timestamp not in the future (beyond policy skew), and the
    receipt must be bound to the same provider card, stream, filter
    fingerprint, grader/grade filter, head walk and committed collection run.
    """
    right = walk.get("rightEdge")
    if right is None:
        return None, ["RIGHT_EDGE_UNRECONCILED"]
    if not isinstance(right, Mapping) or not isinstance(right.get("completed"), bool):
        return None, ["RIGHT_EDGE_INVALID"]
    if right["completed"] is False:
        return None, ["RIGHT_EDGE_UNRECONCILED"]
    reconciled = _typed_timestamp(right.get("reconciledThrough"))
    if reconciled is None:
        return None, ["RIGHT_EDGE_INVALID"]
    why: list[str] = []
    if reconciled > evaluated_at + timedelta(seconds=policy.future_timestamp_skew_seconds):
        why.append("RIGHT_EDGE_IN_FUTURE")
    for edge_key, walk_key in _RIGHT_EDGE_BINDING:
        edge_value, walk_value = right.get(edge_key), walk.get(walk_key)
        norm = [None if v is None else str(v).strip() for v in (edge_value, walk_value)]
        if norm[0] != norm[1]:
            why.append("RIGHT_EDGE_BINDING_MISMATCH")
            break
    if right.get("committed") is not True:
        why.append("RIGHT_EDGE_BINDING_MISMATCH")
    return (None, why) if why else (reconciled, [])


def _stream_reasons(walk: Mapping[str, Any], grading: GradingIdentity) -> list[str]:
    stream = walk.get("stream")
    if stream == "COMBINED":
        return [] if walk.get("combinedSemanticsVerified") is True else ["COMBINED_STREAM_SEMANTICS_UNPROVEN"]
    if stream == "RAW_ONLY":
        return [] if grading.state == "RAW" else ["STREAM_DOES_NOT_COVER_TIER"]
    if stream == "GRADE_FILTERED":
        # A provider grader+grade filter covers every qualifier of that grade.
        same = (grading.state in {"GRADED", "GRADED_QUALIFIED"}
                and str(walk.get("graderFilter") or "").upper() == grading.grader
                and str(walk.get("gradeFilter") or "") == grading.grade)
        return [] if same else ["STREAM_DOES_NOT_COVER_TIER"]
    return ["STREAM_DOES_NOT_COVER_TIER"]


@dataclass(frozen=True)
class WindowReadiness:
    state: str
    reasons: tuple[str, ...]
    proven_lower_bound_date: str | None
    exhausted: bool
    reconciled_through: str | None

    def as_contract(self) -> dict[str, Any]:
        return {"state": self.state, "reasons": list(self.reasons),
                "provenLowerBoundDate": self.proven_lower_bound_date,
                "exhausted": self.exhausted, "reconciledThrough": self.reconciled_through}


def evaluate_walk_for_window(
    walk: Mapping[str, Any] | None, *, window_start: date, window_end: date,
    grading: GradingIdentity, evaluated_at: datetime, provider_card_id: Any = None,
    window_ingested_ats: Sequence[datetime] = (), policy: DisplayPolicy = DEFAULT_POLICY,
) -> WindowReadiness:
    """Readiness of one closed window from one auditable cursor-walk receipt.

    Completeness is proven ONLY by: a typed, date-descending, filter-stable,
    cursor-continuous walk from a known head, bound to ``provider_card_id``
    and a committed collection run, reaching strictly beyond the window's
    lower boundary date (or exhausting the stream with ``hasMore is False``),
    plus a completed, bound, non-future right-edge reconciliation after the
    window's last day ended. Oldest stored date, stored record counts and sync
    status are not accepted as inputs. ``provider_card_id`` omitted means the
    binding cannot be verified, which fails closed (WALK_BINDING_MISMATCH).
    """
    if not walk:
        return WindowReadiness("NOT_COLLECTED", ("NOT_COLLECTED",), None, False, None)
    structural = _walk_structure_reasons(walk, evaluated_at.date())
    if "NOT_COLLECTED" in structural:
        return WindowReadiness("NOT_COLLECTED", tuple(reasons(structural)), None, False, None)
    stream = _stream_reasons(walk, grading)
    binding = _walk_binding_reasons(walk, provider_card_id)
    pages = [page if isinstance(page, Mapping) else {} for page in walk["pages"]]
    # Only an explicit False is exhaustion; null/absent/"false" is unknown.
    exhausted = pages[-1].get("hasMore") is False

    fatal = reasons(structural, stream, binding)
    if fatal:
        return WindowReadiness("UNPROVEN", tuple(fatal), None, exhausted, None)

    rows_pages = [page for page in pages if page["rowCount"] > 0]
    lowest = _typed_date(rows_pages[-1]["minSoldAt"]) if rows_pages else None
    reconciled, right_why = _right_edge(walk, evaluated_at, policy)

    why: list[str] = []
    partial: list[str] = []
    if exhausted:
        lower_ok, lower_bound = True, None
    elif lowest is None:
        lower_ok, lower_bound = False, None
        why.append("LOWER_BOUNDARY_NOT_REACHED")
    else:
        lower_bound = (lowest + timedelta(days=1)).isoformat()
        if lowest < window_start:
            lower_ok = True
        elif lowest == window_start:
            lower_ok = False
            partial.append("BOUNDARY_DATE_PARTIALLY_FETCHED")
        else:
            lower_ok = False
            why.append("LOWER_BOUNDARY_NOT_REACHED")

    right_ok = True
    if reconciled is None:
        right_ok = False
        partial.extend(right_why)
    else:
        if reconciled.date() <= window_end:
            right_ok = False
            partial.append("RIGHT_EDGE_DAY_OPEN")
        if evaluated_at - reconciled > timedelta(hours=policy.sold_head_receipt_max_age_hours):
            right_ok = False
            partial.append("RIGHT_EDGE_STALE")
        if any(ts > reconciled for ts in window_ingested_ats):
            right_ok = False
            partial.append("LATE_INGESTION_AFTER_RECONCILIATION")

    if lower_ok and right_ok:
        return WindowReadiness("PROVEN", (), lower_bound, exhausted, iso_utc(reconciled))
    # Observed facts exist but completeness is not proven. A walk that never
    # reached the lower boundary is UNPROVEN; a walk that reached it but
    # stopped inside the boundary date, or lacks right-edge proof, is PARTIAL.
    state = "PARTIAL" if (lower_ok or "BOUNDARY_DATE_PARTIALLY_FETCHED" in partial) else "UNPROVEN"
    return WindowReadiness(state, tuple(reasons(why, partial)), lower_bound, exhausted, iso_utc(reconciled))


def best_window_readiness(walks: Sequence[Mapping[str, Any]], **kwargs: Any) -> WindowReadiness:
    if not walks:
        return evaluate_walk_for_window(None, **kwargs)
    results = [evaluate_walk_for_window(walk, **kwargs) for walk in walks]
    return sorted(results, key=lambda r: (-READINESS_ORDER[r.state], len(r.reasons), r.reasons))[0]


def readiness_from_sync_state(sync_state: Mapping[str, Any] | None) -> WindowReadiness:
    """A sync-state row alone NEVER proves a window, whatever its status says."""
    if not sync_state:
        return WindowReadiness("NOT_COLLECTED", ("NOT_COLLECTED",), None, False, None)
    return WindowReadiness("UNPROVEN", ("SYNC_STATUS_NOT_PROOF",), None, False, None)


def checkpoint_advance_decision(walk: Mapping[str, Any]) -> dict[str, Any]:
    """Advisory only: may a collector advance its ingestion watermark?

    This bucket advances nothing. The rule is frozen for the collector
    workstream:

    * ``order == "sold_desc"`` (the provider's actual walk): only after the
      whole filtered walk drained (``hasMore is False`` -- an absent or null
      ``hasMore`` is unknown pagination, never a drained walk). Rows ingested
      after the previous watermark can sit on any later page.
    * ``order == "ingested_asc"``: a partial advance is allowed only to the
      greatest ingestion timestamp STRICTLY below the last drained page's
      maximum, because more rows sharing that timestamp may be on the next
      page (same-ingestion-timestamp pages must drain first).
    """
    pages = list(walk.get("pages") or [])
    structural = [code for code in _walk_structure_reasons({**walk, "sort": "date_desc"})
                  if code not in {"WALK_NOT_DATE_DESCENDING"}]
    if structural:
        return {"allowed": False, "watermark": None, "reasons": reasons(structural)}
    stamps = sorted(parse_timestamp(ts) for page in pages for ts in (page.get("ingestedAts") or []))
    if not stamps:
        return {"allowed": False, "watermark": None, "reasons": reasons("NOT_COLLECTED")}
    drained = pages[-1].get("hasMore") is False
    if drained:
        return {"allowed": True, "watermark": iso_utc(stamps[-1]), "reasons": []}
    if walk.get("order") != "ingested_asc":
        return {"allowed": False, "watermark": None, "reasons": reasons("CHECKPOINT_PAGES_PENDING")}
    boundary = max(parse_timestamp(ts) for ts in pages[-1].get("ingestedAts") or [])
    below = [ts for ts in stamps if ts < boundary]
    if not below:
        return {"allowed": False, "watermark": None,
                "reasons": reasons("SAME_INGESTION_TIMESTAMP_UNDRAINED")}
    return {"allowed": True, "watermark": iso_utc(below[-1]),
            "reasons": reasons("SAME_INGESTION_TIMESTAMP_UNDRAINED")}


# ---------------------------------------------------------------------------
# 5. Source freshness and supply provenance.
# ---------------------------------------------------------------------------
PROVENANCE_EXPLICIT = "EXPLICIT"
PROVENANCE_UNKNOWN = "UNKNOWN"
PROVENANCE_DEFAULTED = "DEFAULTED"
PROVENANCE_LEGACY = "LEGACY_UNVERIFIED"


def classify_offer_provenance(provider_row: Mapping[str, Any]) -> dict[str, Any]:
    """Provenance for a NEW raw provider offer (collector handoff rule).

    The existing normalizer maps a missing shipping price to 0.00 and a
    missing quantity to 1; this rule keeps "explicit free shipping" distinct
    from "shipping unknown" and "proven quantity" distinct from "defaulted".
    """
    shipping_raw = provider_row.get("shipping_price")
    if "shipping_price" not in provider_row or shipping_raw is None or str(shipping_raw).strip() == "":
        shipping, shipping_prov = None, PROVENANCE_UNKNOWN
    else:
        shipping, shipping_prov = money(shipping_raw), PROVENANCE_EXPLICIT
    quantity_raw = provider_row.get("quantity")
    if quantity_raw is None or str(quantity_raw).strip() == "":
        quantity, quantity_prov = 1, PROVENANCE_DEFAULTED
    else:
        try:
            quantity = int(str(quantity_raw))
        except ValueError as exc:
            raise ValueError("invalid listing quantity") from exc
        if quantity <= 0:
            raise ValueError("invalid listing quantity")
        quantity_prov = PROVENANCE_EXPLICIT
    return {"itemPrice": money(provider_row.get("price")), "shippingPrice": shipping,
            "shippingProvenance": shipping_prov, "quantity": quantity,
            "quantityProvenance": quantity_prov}


def legacy_offer_provenance(stored_row: Mapping[str, Any]) -> dict[str, Any]:
    """Stored rows written before provenance existed stay LEGACY_UNVERIFIED.

    Provenance is read only from explicit markers written at collection time;
    it is never reconstructed from a stored 0.00 shipping or quantity of 1.
    """
    payload = stored_row.get("source_payload") or {}
    shipping_prov = payload.get("shipping_provenance")
    quantity_prov = payload.get("quantity_provenance")
    shipping = stored_row.get("shipping_price")
    return {
        "itemPrice": money(stored_row.get("item_price")),
        "shippingPrice": money(shipping) if shipping is not None and shipping_prov == PROVENANCE_EXPLICIT else None,
        "shippingProvenance": shipping_prov if shipping_prov in {PROVENANCE_EXPLICIT, PROVENANCE_UNKNOWN} else PROVENANCE_LEGACY,
        "quantity": int(stored_row.get("quantity") or 1),
        "quantityProvenance": quantity_prov if quantity_prov in {PROVENANCE_EXPLICIT, PROVENANCE_DEFAULTED} else PROVENANCE_LEGACY,
    }


def _offer_lowest(offers: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Lowest ask over ``offers`` with shipping provenance carried as basis."""
    if not offers:
        return None
    shipping_states = {o.get("shippingProvenance") or PROVENANCE_LEGACY for o in offers}
    if shipping_states == {PROVENANCE_EXPLICIT}:
        landed = min(money(o["itemPrice"]) + money(o["shippingPrice"]) for o in offers)
        return {"basis": "LANDED_PROVEN", "price": money_json(landed)}
    basis = "ITEM_ONLY_LEGACY_UNVERIFIED" if PROVENANCE_LEGACY in shipping_states else "ITEM_ONLY"
    return {"basis": basis, "price": money_json(min(money(o["itemPrice"]) for o in offers))}


def _provenance_reasons(offers: Sequence[Mapping[str, Any]]) -> list[str]:
    why: list[str] = []
    shipping_states = {o.get("shippingProvenance") or PROVENANCE_LEGACY for o in offers}
    quantity_states = {o.get("quantityProvenance") or PROVENANCE_LEGACY for o in offers}
    if PROVENANCE_UNKNOWN in shipping_states:
        why.append("SHIPPING_UNKNOWN")
    if PROVENANCE_LEGACY in shipping_states:
        why.append("SHIPPING_LEGACY_UNVERIFIED")
    if PROVENANCE_DEFAULTED in quantity_states:
        why.append("QUANTITY_DEFAULTED")
    if PROVENANCE_LEGACY in quantity_states:
        why.append("QUANTITY_LEGACY_UNVERIFIED")
    return why


def _captured_quantity(offers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    states = {o.get("quantityProvenance") or PROVENANCE_LEGACY for o in offers}
    provenance = ("PROVEN" if states == {PROVENANCE_EXPLICIT}
                  else PROVENANCE_LEGACY if PROVENANCE_LEGACY in states
                  else "DEFAULTED_LOWER_BOUND")
    return {"value": sum(int(o.get("quantity") or 1) for o in offers), "provenance": provenance}


def evaluate_supply_snapshot(snapshot: Mapping[str, Any] | None, *, evaluated_at: datetime,
                             previous_confirmation: Any = None,
                             policy: DisplayPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """Current-ask readiness from PROVIDER confirmation only (supply v2).

    * Offers are split: **confirmed** (a valid, non-future provider
      confirmation) versus **unconfirmed** (missing/unparseable confirmation, or
      one beyond the future skew). Unconfirmed offers never set the lowest ask,
      the captured listing count, the captured quantity or the depth; they are
      reported separately under ``unconfirmedOffers`` with their provenance.
    * A snapshot is ``FRESH`` (current) only when EVERY captured offer is
      confirmed and the oldest confirmation is within policy. A mix of
      confirmed and unconfirmed offers is ``PARTIALLY_CONFIRMED``: facts are
      shown as last-known, the current capability is withheld.
    * ``hasMore`` must be a real boolean: True -> LOWER_BOUND, False ->
      COMPLETE_AT_SOURCE, anything else -> depth UNKNOWN
      (SUPPLY_PAGINATION_UNKNOWN). An empty response proves zero only with
      ``hasMore is False`` AND a fresh provider ``sourceConfirmedAt``; an empty
      response that claims more pages is contradictory, never zero.
    * ``currentUntil`` = oldest confirmation + policy age: the instant at which
      a cached current generation stops being current (see
      ``reevaluate_capabilities``).

    ``observedAt`` (local collection time) and ``listingUpdatedAt`` are
    carried as labelled facts but never establish freshness.
    """
    base = {"source": ASK_SOURCE, "conditionBasis": ASK_CONDITION_BASIS, "providerConfirmedAt": None,
            "confirmationAgeHours": None, "currentUntil": None, "collectedAt": None,
            "offerQualification": "NOT_CURRENT", "capturedListingCount": None, "capturedQuantity": None,
            "depth": None, "lowestAsk": None, "unconfirmedOffers": None}
    if not snapshot:
        return {**base, "state": "NOT_COLLECTED", "reasons": reasons("NOT_COLLECTED")}
    base["collectedAt"] = iso_utc(_typed_timestamp(snapshot.get("observedAt")))
    if snapshot.get("observationState") != "OBSERVED":
        return {**base, "state": "COLLECTION_FAILED", "reasons": reasons("SUPPLY_COLLECTION_FAILED")}
    offers = list(snapshot.get("offers") or [])
    has_more = snapshot.get("hasMore")
    skew = timedelta(seconds=policy.future_timestamp_skew_seconds)
    max_age = timedelta(hours=policy.ask_confirmation_max_age_hours)
    why: list[str] = []
    if has_more is True:
        why.append("DEPTH_TRUNCATED")
    elif has_more is not False:
        why.append("SUPPLY_PAGINATION_UNKNOWN")

    if not offers:
        if has_more is True:
            return {**base, "state": "ZERO_UNPROVEN",
                    "reasons": reasons("SUPPLY_PAGINATION_CONTRADICTORY")}
        if has_more is not False:
            return {**base, "state": "ZERO_UNPROVEN", "reasons": reasons(why)}
        confirmed = _typed_timestamp(snapshot.get("sourceConfirmedAt"))
        if confirmed is None:
            return {**base, "state": "ZERO_UNPROVEN", "reasons": reasons(why, "EMPTY_WITHOUT_SOURCE_FRESHNESS")}
        if confirmed > evaluated_at + skew:
            return {**base, "state": "CONFIRMATION_INVALID", "reasons": reasons(why, "SOURCE_CONFIRMATION_IN_FUTURE")}
        age = evaluated_at - confirmed
        base.update(providerConfirmedAt=iso_utc(confirmed), confirmationAgeHours=_hours(age),
                    capturedListingCount=0, capturedQuantity={"value": 0, "provenance": PROVENANCE_EXPLICIT},
                    depth="COMPLETE_AT_SOURCE")
        if age > max_age:
            return {**base, "state": "STALE", "reasons": reasons(why, "ASKS_STALE")}
        return {**base, "state": "ZERO_PROVEN", "reasons": reasons(why), "offerQualification": "CURRENT",
                "currentUntil": iso_utc(confirmed + max_age)}

    confirmed_offers: list[tuple[datetime, Mapping[str, Any]]] = []
    missing: list[Mapping[str, Any]] = []
    future: list[Mapping[str, Any]] = []
    for offer in offers:
        ts = _typed_timestamp(offer.get("providerSnapshotAt"))
        if ts is None:
            missing.append(offer)
        elif ts > evaluated_at + skew:
            future.append(offer)
        else:
            confirmed_offers.append((ts, offer))
    if missing:
        why.append("SOURCE_CONFIRMATION_MISSING")
    if future:
        why.append("SOURCE_CONFIRMATION_IN_FUTURE")
    excluded = missing + future
    if excluded:
        why.append("UNCONFIRMED_OFFERS_EXCLUDED")
        base["unconfirmedOffers"] = {"count": len(missing), "futureCount": len(future),
                                     "capturedQuantity": _captured_quantity(excluded),
                                     "lowestAsk": _offer_lowest(excluded),
                                     "reasons": reasons(_provenance_reasons(excluded))}
    if len({ts for ts, _ in confirmed_offers}) > 1:
        why.append("SOURCE_CONFIRMATION_MIXED")

    usable = [offer for _, offer in confirmed_offers]
    why.extend(_provenance_reasons(usable))
    if has_more is not True and has_more is not False:
        base["depth"] = "UNKNOWN"
    elif has_more is True or excluded:
        # Excluded (unconfirmed) offers mean the confirmed set is a subset.
        base["depth"] = "LOWER_BOUND"
    else:
        base["depth"] = "COMPLETE_AT_SOURCE"
    if not usable:
        state = "CONFIRMATION_INVALID" if future and not missing else "CONFIRMATION_MISSING"
        return {**base, "depth": None, "state": state, "reasons": reasons(why)}

    base["capturedListingCount"] = len(usable)
    base["capturedQuantity"] = _captured_quantity(usable)
    base["lowestAsk"] = _offer_lowest(usable)
    confirmed = min(ts for ts, _ in confirmed_offers)
    previous = _typed_timestamp(previous_confirmation)
    if previous is not None and previous == confirmed:
        why.append("SOURCE_CONFIRMATION_REPEATED")
    age = evaluated_at - confirmed
    base.update(providerConfirmedAt=iso_utc(confirmed), confirmationAgeHours=_hours(age))
    if age > max_age:
        return {**base, "state": "STALE", "reasons": reasons(why, "ASKS_STALE")}
    if excluded:
        return {**base, "state": "PARTIALLY_CONFIRMED", "reasons": reasons(why)}
    return {**base, "state": "FRESH", "reasons": reasons(why), "offerQualification": "CURRENT",
            "currentUntil": iso_utc(confirmed + max_age)}


def _hours(delta: timedelta) -> str:
    return str((Decimal(int(delta.total_seconds())) / Decimal(3600)).quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN))


# ---------------------------------------------------------------------------
# 6. Group membership (CURRENT_ROSTER_RETROSPECTIVE) and pins (membership v2).
# ---------------------------------------------------------------------------
REVISION_KINDS = ("SURFACE_V2_GENERATION", "QUERY_CACHE_PUBLISHED_REVISION", "QUERY_CACHE_FINGERPRINT")
ACTIVITY_GENERATION_STATES = ("SERVING", "RETAINED", "RETIRED")
CUSTOM_MARKET_PREFIX = "custom:"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def validate_roster_revision(revision: Mapping[str, Any] | None) -> list[str]:
    """A roster revision (``rosterRef``) must name an immutable published snapshot.

    * SURFACE_V2_GENERATION (prepared markets): generationId + marketKey; the
      V2 constituents table is keyed by (generation_id, market_key, rank) and a
      generation is never mutated after promotion.
    * QUERY_CACHE_PUBLISHED_REVISION (custom markets): the FMA-1 sidecar (see
      SCHEMA_DECISION.md) -- SHA-256 query fingerprint + immutable revision UUID
      + computedThrough date.
    * A bare query fingerprint is a SPECIFICATION: the custom cache row and its
      constituent detail are replaced in place on rebuild, so pages read across
      a rebuild can mix rosters. It is rejected.
    """
    if not isinstance(revision, Mapping):
        return reasons("ROSTER_REVISION_UNSTABLE")
    kind = revision.get("kind")
    if kind == "SURFACE_V2_GENERATION":
        ok = bool(_UUID.match(str(revision.get("generationId") or "").lower())) and _nonempty_text(
            revision.get("marketKey"))
        return [] if ok else reasons("ROSTER_REVISION_UNSTABLE")
    if kind == "QUERY_CACHE_PUBLISHED_REVISION":
        ok = (bool(_SHA256.match(str(revision.get("queryFingerprint") or "")))
              and bool(_UUID.match(str(revision.get("revisionId") or "").lower()))
              and _typed_date(revision.get("computedThrough")) is not None)
        return [] if ok else reasons("ROSTER_REVISION_UNSTABLE")
    if kind == "QUERY_CACHE_FINGERPRINT":
        return reasons("QUERY_FINGERPRINT_IS_NOT_A_REVISION", "ROSTER_REVISION_UNSTABLE")
    return reasons("ROSTER_REVISION_UNSTABLE")


def custom_market_key(query_fingerprint: str) -> str:
    """Custom markets are addressed as ``custom:{queryFingerprint}``; the
    roster itself is pinned by the published revision, never by the key."""
    return f"{CUSTOM_MARKET_PREFIX}{query_fingerprint}"


def roster_contract(*, revision: Mapping[str, Any], roster_as_of: Any, roster_denominator: int) -> dict[str, Any]:
    if int(roster_denominator) < 0:
        raise ValueError("roster denominator must be non-negative")
    return {"membershipMode": MEMBERSHIP_MODE, "label": MEMBERSHIP_LABEL,
            "membershipContractVersion": MEMBERSHIP_CONTRACT_VERSION,
            "rosterAsOf": parse_date(roster_as_of).isoformat(),
            "rosterRevision": dict(revision), "rosterDenominator": int(roster_denominator)}


def check_generation(requested: Any, served: Any) -> list[str]:
    if not requested or not served or str(requested).lower() != str(served).lower():
        return reasons("GENERATION_MISMATCH")
    return []


def check_asset(asset: Any) -> list[str]:
    return [] if asset in SUPPORTED_ASSETS else reasons("UNSUPPORTED_ASSET")


def check_pins(request: Mapping[str, Any], inputs: Mapping[str, Any]) -> list[str]:
    """Validate the three independent pins of every activity read.

    1. ``activityGenerationId`` -- the immutable activity projection. It must
       equal the generation the reader resolved; a RETIRED generation is
       ACTIVITY_GENERATION_EXPIRED (restart from the first page).
    2. ``rosterRef`` -- the immutable roster (prepared V2 generation or custom
       published revision). It must equal the roster the activity generation
       was built on (ROSTER_REVISION_MISMATCH otherwise), and for a prepared
       market its surface generation must equal the served one
       (GENERATION_MISMATCH).
    3. ``marketKey`` -- must be the roster's market key (prepared) or
       ``custom:{queryFingerprint}`` (custom). Activity never invokes the
       canonical query builder to resolve a custom market.
    """
    why = list(check_asset(inputs.get("asset")))
    ref = request.get("rosterRef")
    ref_why = validate_roster_revision(ref)
    why.extend(ref_why)
    generation = inputs.get("activityGeneration") if isinstance(inputs.get("activityGeneration"), Mapping) else {}
    requested = str(request.get("activityGenerationId") or "").lower()
    resolved = str(generation.get("activityGenerationId") or "").lower()
    pinned = bool(_UUID.match(requested)) and requested == resolved
    if not pinned:
        why.append("ACTIVITY_GENERATION_MISMATCH")
    elif generation.get("state") not in ("SERVING", "RETAINED"):
        why.append("ACTIVITY_GENERATION_EXPIRED")
    if not ref_why:
        if pinned and canonical_json(generation.get("rosterRef")) != canonical_json(ref):
            why.append("ROSTER_REVISION_MISMATCH")
        if ref["kind"] == "SURFACE_V2_GENERATION":
            why.extend(check_generation(ref.get("generationId"), inputs.get("servedGenerationId")))
            if ref.get("marketKey") != request.get("marketKey"):
                why.append("ROSTER_REVISION_MISMATCH")
        elif request.get("marketKey") != custom_market_key(ref["queryFingerprint"]):
            why.append("ROSTER_REVISION_MISMATCH")
    return reasons(why)


def validate_members(members: Any, denominator: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """Full-roster integrity: unique contiguous ranks 1..N, unique variants and
    instrument keys, N == denominator. Returns members sorted by rank."""
    bad = ([], reasons("ROSTER_INTEGRITY_VIOLATION"))
    if not _is_count(denominator) or not isinstance(members, (list, tuple)) or len(members) != denominator:
        return bad
    rows: list[dict[str, Any]] = []
    for member in members:
        if not isinstance(member, Mapping) or not _is_count(member.get("rank")):
            return bad
        variant = str(member.get("cardVariantId") or "").lower()
        try:
            parsed = parse_instrument_key(member.get("instrumentKey"))
        except ValueError:
            return bad
        if not _UUID.match(variant) or parsed["cardVariantId"] != variant:
            return bad
        rows.append(dict(member))
    rows.sort(key=lambda m: m["rank"])
    if [m["rank"] for m in rows] != list(range(1, denominator + 1)):
        return bad
    if len({str(m["cardVariantId"]).lower() for m in rows}) != len(rows):
        return bad
    if len({m["instrumentKey"] for m in rows}) != len(rows):
        return bad
    return rows, []


def _cursor_payload(request: Mapping[str, Any], window_days: int, after_rank: int) -> dict[str, Any]:
    return {"v": CURSOR_VERSION, "a": str(request.get("activityGenerationId") or "").lower(),
            "r": fingerprint(request.get("rosterRef")), "m": request.get("marketKey"),
            "d": parse_date(request["asOf"]).isoformat(), "w": int(window_days), "k": int(after_rank)}


def encode_cursor(payload: Mapping[str, Any]) -> str:
    """Opaque, revision-bound page cursor: ``fmac1.<hex(canonical json)>.<check>``.

    Binds cursor version, activity generation, roster ref (SHA-256), market,
    asOf and window. Clients must treat it as opaque. It is integrity-checked,
    not secret: tampering can only request another page of the same pins,
    which the reader re-validates.
    """
    return f"fmac1.{canonical_json(dict(payload)).encode('ascii').hex()}.{fingerprint(dict(payload))[:16]}"


def decode_cursor(cursor: Any) -> dict[str, Any]:
    if not isinstance(cursor, str):
        raise ValueError("cursor must be a string")
    parts = cursor.split(".")
    if len(parts) != 3 or parts[0] != "fmac1":
        raise ValueError("unknown cursor format")
    try:
        payload = json.loads(bytes.fromhex(parts[1]).decode("ascii"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("undecodable cursor") from exc
    if not isinstance(payload, dict) or set(payload) != {"v", "a", "r", "m", "d", "w", "k"}:
        raise ValueError("cursor payload shape")
    if fingerprint(payload)[:16] != parts[2] or payload["v"] != CURSOR_VERSION or not _is_count(payload["k"]):
        raise ValueError("cursor integrity")
    return payload


# ---------------------------------------------------------------------------
# 7. Metrics and peers.
# ---------------------------------------------------------------------------
def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return median.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)


def price_summary(prices: Sequence[Any], *, policy: DisplayPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """Median/low/high of ONE exact tier. Raw and graded never share a call."""
    values = sorted(money(p) for p in prices)
    out = {"recordCount": len(values), "median": None, "low": None, "high": None}
    if not values:
        return {**out, "state": "NO_RECORDS", "reasons": reasons("NO_RECORDS")}
    if len(values) < policy.price_summary_min_records:
        return {**out, "state": "THIN", "reasons": reasons("THIN_RECORDS")}
    return {**out, "state": "AVAILABLE", "reasons": [], "median": money_json(_median(values)),
            "low": money_json(values[0]), "high": money_json(values[-1])}


PEER_SCOPE_KINDS = ("RESEARCH_PANEL", "MARKET_ROSTER")
MARKET_ROSTER_SCOPE_LABEL = "Current constituents of this market"


def population_scope(panel_id: str) -> dict[str, Any]:
    if panel_id != RESEARCH_PANEL_ID:
        raise ValueError("V1 research-panel peers are defined only on the frozen research panel")
    return {"panelId": RESEARCH_PANEL_ID, "scopeLabel": RESEARCH_PANEL_SCOPE_LABEL, "claimsAllPokemon": False}


def peer_scope(scope: Mapping[str, Any] | None, *, roster_ref: Mapping[str, Any] | None = None,
               activity_generation_id: Any = None) -> dict[str, Any]:
    """Explicit contextual peer scope (peer population v2).

    Every peer population names WHICH cohort it is and WHICH revision of it:

    * RESEARCH_PANEL -- the frozen Core Panel V1; ``cohortRevision`` names the
      panel/evidence revision the peer values were computed from.
    * MARKET_ROSTER -- the current constituents of THIS market; ``rosterRef``
      must equal the response roster and ``cohortRevision`` must equal the
      pinned activity generation.

    No scope is "all Pokemon" and populations of different scopes or revisions
    never share a population key.
    """
    if not isinstance(scope, Mapping) or not _nonempty_text(scope.get("cohortRevision")):
        raise ValueError("peer scope requires kind and cohortRevision")
    kind, cohort = scope.get("kind"), str(scope["cohortRevision"]).strip()
    if kind == "RESEARCH_PANEL":
        population_scope(scope.get("panelId"))
        return {"kind": kind, "scopeId": RESEARCH_PANEL_ID, "scopeLabel": RESEARCH_PANEL_SCOPE_LABEL,
                "cohortRevision": cohort, "claimsAllPokemon": False}
    if kind == "MARKET_ROSTER":
        if roster_ref is None or canonical_json(scope.get("rosterRef")) != canonical_json(roster_ref):
            raise ValueError("MARKET_ROSTER peer scope must name the response roster")
        if cohort.lower() != str(activity_generation_id or "").lower():
            raise ValueError("MARKET_ROSTER cohortRevision must be the pinned activity generation")
        return {"kind": kind, "scopeId": fingerprint(roster_ref), "scopeLabel": MARKET_ROSTER_SCOPE_LABEL,
                "cohortRevision": cohort.lower(), "claimsAllPokemon": False}
    raise ValueError(f"unsupported peer scope kind {kind!r}")


def peer_scope_key(scope: Mapping[str, Any]) -> str:
    return f"{scope['kind']}:{scope['scopeId']}@{scope['cohortRevision']}"


def peer_population_key(*, window_start: Any, window_end: Any, source: str, currency: str, tier: str,
                        coverage: str, scope_key: str) -> str:
    """Peers are comparable only on the SAME actual dated window (not merely
    the same duration), source, currency, tier, coverage and scoped cohort
    revision."""
    return (f"{parse_date(window_start).isoformat()}..{parse_date(window_end).isoformat()}"
            f"|{source}|{currency}|{tier}|{coverage}|{scope_key}")


def activity_percentile(target_key: str, target_value: int | None, peers: Sequence[Mapping[str, Any]], *,
                        population_key: str, policy: DisplayPolicy = DEFAULT_POLICY,
                        scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Midrank "Activity percentile" against OTHER unique eligible peers.

    * peers must share the exact population key; the target is excluded;
    * the denominator counts UNIQUE peer instruments: repeated rows for one
      instrument with the same value count once (``duplicatePeerRowCount``),
      and an instrument with conflicting or invalid values is quarantined
      (``quarantinedPeerCount``) -- it never counts toward the threshold;
    * midrank = (strictly-below + 0.5 * ties) / N; the literal
      ``strictBelowPct`` counts strictly-below only, never half the ties;
    * thin (N < policy), all-zero and all-tied populations are explicit states.
    """
    candidate_rows = [p for p in peers if isinstance(p, Mapping) and _nonempty_text(p.get("instrumentKey"))
                      and p.get("instrumentKey") != target_key and p.get("populationKey") == population_key
                      and p.get("value") is not None]
    by_instrument: dict[str, set[Any]] = {}
    for row in candidate_rows:
        value = row["value"]
        by_instrument.setdefault(str(row["instrumentKey"]), set()).add(
            value if _is_count(value) else ("INVALID", repr(value)))
    values = [next(iter(vals)) for vals in by_instrument.values() if len(vals) == 1 and _is_count(next(iter(vals)))]
    quarantined = len(by_instrument) - len(values)
    n = len(values)
    out = {"label": PERCENTILE_LABEL, "tiePolicy": TIE_POLICY_VERSION, "populationKey": population_key,
           "eligibleOtherPeerCount": n, "quarantinedPeerCount": quarantined,
           "duplicatePeerRowCount": len(candidate_rows) - len(by_instrument),
           "activityPercentile": None, "strictBelowPct": None, "tieCount": None,
           "scope": dict(scope) if scope else None,
           "scopeLabel": (scope or {}).get("scopeLabel"), "claimsAllPokemon": False}
    if target_value is None:
        return {**out, "state": "UNAVAILABLE", "reasons": reasons("WINDOW_NOT_PROVEN")}
    if n == 0:
        return {**out, "state": "NO_PEERS", "reasons": reasons("NO_PEERS")}
    below = sum(v < target_value for v in values)
    ties = sum(v == target_value for v in values)
    out["tieCount"] = ties
    if n < policy.percentile_min_other_peers:
        return {**out, "state": "INSUFFICIENT_PEERS", "reasons": reasons("INSUFFICIENT_PEERS")}
    if target_value == 0 and all(v == 0 for v in values):
        return {**out, "state": "ALL_ZERO", "reasons": reasons("ALL_ZERO")}
    if ties == n:
        return {**out, "state": "ALL_TIED", "reasons": reasons("ALL_PEERS_TIED")}
    midrank = Decimal(below) + Decimal(ties) / 2
    return {**out, "state": "AVAILABLE", "reasons": [],
            "activityPercentile": str((midrank * 100 / n).quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN)),
            "strictBelowPct": pct_string(below, n)}


def window_change(current: int | None, baseline: int | None) -> dict[str, Any]:
    """Change in activity versus a prior window. Zero is not missing."""
    if current is None or baseline is None:
        return {"state": "UNAVAILABLE", "changePct": None, "reasons": reasons("BASELINE_MISSING")}
    if baseline == 0 and current == 0:
        return {"state": "NO_ACTIVITY", "changePct": None, "reasons": reasons("ALL_ZERO")}
    if baseline == 0:
        return {"state": "ZERO_BASELINE", "changePct": None, "reasons": reasons("ZERO_BASELINE")}
    change = (Decimal(current) - Decimal(baseline)) * 100 / Decimal(baseline)
    return {"state": "AVAILABLE", "changePct": str(change.quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN)),
            "reasons": []}


# ---------------------------------------------------------------------------
# Per-feature capabilities and independent availability dimensions.
# ---------------------------------------------------------------------------
FEATURES = ("saleCount", "observedSales", "salePriceSummary", "activityPercentile", "currentAsks",
            "askDepth", "landedAsk", "supplyTurnover", "inferredSalesFromListings")
EXPIRING_FEATURES = ("currentAsks", "askDepth", "landedAsk")
CURRENT_ASK_STATES = ("FRESH", "ZERO_PROVEN")


def feature_capabilities(*, fatal: Sequence[str], window: WindowReadiness | None,
                         identity_ok: bool, summary: Mapping[str, Any] | None,
                         peers: Mapping[str, Any] | None, asks: Mapping[str, Any] | None,
                         observation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Per-feature capabilities.

    * ``saleCount`` / ``salePriceSummary`` / ``activityPercentile`` are
      complete-volume capabilities: they need a PROVEN window.
    * ``observedSales`` is the explicit observed-facts capability: exact
      observed counts and dated observations from a known collection, without
      any completeness claim. It never implies ``saleCount``.
    * ``currentAsks`` / ``askDepth`` / ``landedAsk`` carry ``expiresAt``: the
      provider confirmation age limit. A cached generation re-evaluated after
      that instant is no longer current (``reevaluate_capabilities``).
    """
    def cap(ok: bool, why: Iterable[str]) -> dict[str, Any]:
        return {"available": bool(ok), "reasons": [] if ok else reasons(why)}

    def expiring(ok: bool, why: Iterable[str], until: Any) -> dict[str, Any]:
        return {**cap(ok, why), "expiresAt": until if ok else None}

    if fatal:
        caps = {name: cap(False, fatal) for name in FEATURES}
        for name in EXPIRING_FEATURES:
            caps[name]["expiresAt"] = None
        return caps
    window_ok = bool(window and window.state == "PROVEN" and identity_ok)
    if window is None:
        window_why = ["NOT_COLLECTED"]
    elif window.state == "NOT_COLLECTED":
        window_why = list(window.reasons)
    else:
        window_why = list(window.reasons) + ["WINDOW_NOT_PROVEN"]
    caps = {"saleCount": cap(window_ok, window_why)}
    observed_ok = bool(identity_ok and observation and observation.get("state") == "OBSERVED")
    caps["observedSales"] = cap(observed_ok, (observation or {}).get("reasons") or ["NOT_COLLECTED"])
    s_ok = window_ok and bool(summary) and summary.get("state") == "AVAILABLE"
    caps["salePriceSummary"] = cap(s_ok, window_why if not window_ok else (summary or {}).get("reasons") or [])
    p_ok = window_ok and bool(peers) and peers.get("state") == "AVAILABLE"
    caps["activityPercentile"] = cap(p_ok, window_why if not window_ok else (peers or {}).get("reasons") or [])
    a_state = (asks or {}).get("state")
    a_why = (asks or {}).get("reasons") or ["NOT_COLLECTED"]
    until = (asks or {}).get("currentUntil")
    current_ok = a_state in CURRENT_ASK_STATES and until is not None
    caps["currentAsks"] = expiring(current_ok, a_why, until)
    depth_ok = current_ok and (asks or {}).get("depth") in {"COMPLETE_AT_SOURCE", "LOWER_BOUND"}
    caps["askDepth"] = expiring(depth_ok, a_why if not current_ok else ["SUPPLY_PAGINATION_UNKNOWN"], until)
    landed = a_state == "FRESH" and current_ok and ((asks or {}).get("lowestAsk") or {}).get("basis") == "LANDED_PROVEN"
    caps["landedAsk"] = expiring(landed, [c for c in a_why if c != "DEPTH_TRUNCATED"] or ["SHIPPING_UNKNOWN"],
                                 until)
    caps["supplyTurnover"] = cap(False, ["FEATURE_DISABLED_V1"])
    caps["inferredSalesFromListings"] = cap(False, ["FEATURE_DISABLED_V1"])
    return caps


def reevaluate_capabilities(capabilities: Mapping[str, Any], *, at: Any) -> dict[str, Any]:
    """Re-evaluate cached capabilities at read time ``at``.

    A capability with ``expiresAt`` is current only while ``at <= expiresAt``;
    after that instant it is unavailable with ASKS_STALE, so a cached
    generation can never stay current after its provider confirmation aged
    out. Capabilities without expiry are returned unchanged.
    """
    at_ts = parse_timestamp(at)
    out: dict[str, Any] = {}
    for name, capability in capabilities.items():
        expires = capability.get("expiresAt") if isinstance(capability, Mapping) else None
        if capability.get("available") and expires is not None and at_ts > parse_timestamp(expires):
            out[name] = {"available": False, "reasons": reasons("ASKS_STALE"), "expiresAt": expires}
        else:
            out[name] = dict(capability)
    return out


# ---------------------------------------------------------------------------
# Observation (collection evidence) is separate from completeness proof.
# ---------------------------------------------------------------------------
OBSERVATION_BASES = ("WALK_RECEIPT", "COLLECTION_RECORD", "STORED_ROWS")


def sold_observation(*, records: Sequence[Any], walks: Sequence[Any], collection_record: Any,
                     provider_card_id: Any) -> dict[str, Any]:
    """Was sold evidence for THIS provider card ever collected?

    Collection evidence, strongest first: a committed walk receipt bound to
    the provider card; an explicit collection record (e.g. a sync-state row)
    for the card; or stored evidence rows for the card. Any of them makes the
    card OBSERVED: observed counts are exact counts of eligible stored rows and
    zero means "a known collection holds no matching row" -- never proven zero.
    Only the absence of all three is NOT_COLLECTED (null counts).
    Completeness proof is evaluated separately and never inferred from this.
    """
    card = str(provider_card_id).strip() if _nonempty_text(provider_card_id) else None
    bound = card is not None and any(
        isinstance(w, Mapping) and w.get("pages") and str(w.get("providerCardId") or "").strip() == card
        and w.get("committed") is True for w in walks)
    record_ok = (isinstance(collection_record, Mapping) and collection_record.get("collected") is True
                 and card is not None and str(collection_record.get("providerCardId") or "").strip() == card)
    if bound:
        basis = "WALK_RECEIPT"
    elif record_ok:
        basis = "COLLECTION_RECORD"
    elif records:
        basis = "STORED_ROWS"
    else:
        return {"state": "NOT_COLLECTED", "basis": None, "reasons": reasons("NOT_COLLECTED")}
    return {"state": "OBSERVED", "basis": basis,
            "reasons": [] if basis == "WALK_RECEIPT" else reasons("COMPLETENESS_RECEIPT_MISSING")}


# ---------------------------------------------------------------------------
# Dated chart series (fma_activity_series_v1).
# ---------------------------------------------------------------------------
SERIES_STORAGE = "SPARSE_DAILY"
SERIES_ZERO_RULE = "ABSENT_DATE_IS_ZERO_ONLY_INSIDE_PROVEN_SPAN"
SERIES_OUTSIDE_ACTIVITY_RANGE = "NOT_COLLECTED"
GROUP_SUPPLY_AGGREGATION = "LOWER_BOUND_SUM_OF_CONFIRMED_CONSTITUENT_SNAPSHOTS"
SERIES_MAX_DAYS = max(WINDOW_DAYS)


def _date_range(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    start, end = parse_date(value["startDate"]), parse_date(value["endDate"])
    if start > end:
        raise ValueError("chartRange startDate must not follow endDate")
    return {"startDate": start.isoformat(), "endDate": end.isoformat()}


def _span(bounds: tuple[date, date] | None) -> dict[str, str] | None:
    return None if bounds is None else {"startDate": bounds[0].isoformat(), "endDate": bounds[1].isoformat()}


def _in_span(day: date, span: Mapping[str, str] | None) -> bool:
    return bool(span) and parse_date(span["startDate"]) <= day <= parse_date(span["endDate"])


def _series_envelope(as_of: date, chart_range: Any) -> dict[str, Any]:
    return {"version": SERIES_VERSION, "storage": SERIES_STORAGE, "asOf": as_of.isoformat(),
            "zeroRule": SERIES_ZERO_RULE, "outsideActivityRange": SERIES_OUTSIDE_ACTIVITY_RANGE,
            "canonicalRange": _date_range(chart_range),
            "activityRange": _span(closed_window(as_of, SERIES_MAX_DAYS))}


def sales_series(matched: Sequence[Mapping[str, Any]], *, as_of: date, observation: Mapping[str, Any],
                 readiness_by_days: Mapping[int, WindowReadiness], tier: str) -> dict[str, Any]:
    """Sparse daily sold series for one exact instrument.

    One count point and one price point per sold date that holds >= 1
    eligible observation inside the activity range. A date with no point is
    ZERO only inside ``provenSpan`` (the widest PROVEN window); everywhere else
    it is missing. Window totals are never repeated onto dates.
    """
    act_start, act_end = closed_window(as_of, SERIES_MAX_DAYS)
    proven = [days for days in WINDOW_DAYS if readiness_by_days[days].state == "PROVEN"]
    span = _span(closed_window(as_of, max(proven))) if proven else None
    stamps = [parse_timestamp(r.reconciled_through) for r in readiness_by_days.values() if r.reconciled_through]
    reconciled = max(stamps) if stamps else None
    by_date: dict[date, list[Mapping[str, Any]]] = {}
    if observation.get("state") == "OBSERVED":
        for row in matched:
            if act_start <= row["soldAt"] <= act_end:
                by_date.setdefault(row["soldAt"], []).append(row)
    counts, prices = [], []
    for day in sorted(by_date):
        rows = by_date[day]
        ingested = sorted(r["ingestedAt"] for r in rows if r["ingestedAt"] is not None)
        counts.append({"date": day.isoformat(), "observedCount": len(rows),
                       "proofState": "PROVEN" if _in_span(day, span) else "OBSERVED_ONLY",
                       "firstIngestedAt": iso_utc(ingested[0]) if ingested else None,
                       "lastIngestedAt": iso_utc(ingested[-1]) if ingested else None,
                       "ingestedAfterReconciliation": (None if reconciled is None
                                                       else any(ts > reconciled for ts in ingested))})
        values = sorted(r["price"] for r in rows)
        prices.append({"date": day.isoformat(), "recordCount": len(values), "low": money_json(values[0]),
                       "median": money_json(_median(values)), "high": money_json(values[-1])})
    return {"source": SOLD_SOURCE, "conditionBasis": SOLD_CONDITION_BASIS, "currency": SUPPORTED_CURRENCY,
            "tier": tier, "observationState": observation.get("state"), "provenSpan": span,
            "reconciledThrough": iso_utc(reconciled),
            "counts": {"unit": "SALE_COUNT", "points": counts},
            "prices": {"unit": "USD", "points": prices}}


def supply_series(snapshots: Sequence[Any], *, as_of: date, policy: DisplayPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """Offered-supply history, one point per provider-confirmation date.

    * Each snapshot is evaluated at its own collection time (``observedAt``);
      only snapshots carrying a valid provider confirmation become points,
      dated by that confirmation (never by local collection time).
    * Repeated source confirmations (the same ``providerConfirmedAt`` collected
      again) are one point: ``collectionCount`` > 1, first/last collection
      times, values from the first collection. They are not new evidence.
    * Several confirmations on one date: the latest is the point,
      ``confirmationsOnDate`` counts them.
    * A date without a point is MISSING: supply is never zero-filled or
      carried forward. A ZERO_PROVEN snapshot is an explicit 0 point.
    * Listing counts, listed quantity and lowest ask are separate unit axes.
    """
    act_start, act_end = closed_window(as_of, SERIES_MAX_DAYS)
    by_confirmation: dict[str, list[tuple[datetime, dict[str, Any]]]] = {}
    excluded: dict[str, int] = {}
    outside = 0
    for snapshot in snapshots:
        if not isinstance(snapshot, Mapping):
            continue
        collected = _typed_timestamp(snapshot.get("observedAt"))
        if collected is None:
            excluded["COLLECTION_FAILED"] = excluded.get("COLLECTION_FAILED", 0) + 1
            continue
        evaluation = evaluate_supply_snapshot(snapshot, evaluated_at=collected, policy=policy)
        confirmed = evaluation["providerConfirmedAt"]
        if confirmed is None:
            excluded[evaluation["state"]] = excluded.get(evaluation["state"], 0) + 1
            continue
        if not act_start <= parse_timestamp(confirmed).date() <= act_end:
            outside += 1
            continue
        by_confirmation.setdefault(confirmed, []).append((collected, evaluation))
    by_date: dict[str, list[str]] = {}
    for confirmed in by_confirmation:
        by_date.setdefault(confirmed[:10], []).append(confirmed)
    listings, quantity, lowest = [], [], []
    for day in sorted(by_date):
        confirmed = max(by_date[day])
        entries = sorted(by_confirmation[confirmed], key=lambda pair: pair[0])
        first = entries[0][1]
        listings.append({"date": day, "providerConfirmedAt": confirmed,
                         "firstCollectedAt": iso_utc(entries[0][0]), "lastCollectedAt": iso_utc(entries[-1][0]),
                         "collectionCount": len(entries), "confirmationsOnDate": len(by_date[day]),
                         "stateAtCollection": first["state"], "depth": first["depth"],
                         "value": first["capturedListingCount"]})
        quantity.append({"date": day, "providerConfirmedAt": confirmed,
                         "provenance": first["capturedQuantity"]["provenance"],
                         "value": first["capturedQuantity"]["value"]})
        if first["lowestAsk"] is not None:
            lowest.append({"date": day, "providerConfirmedAt": confirmed, **first["lowestAsk"]})
    return {"source": ASK_SOURCE, "conditionBasis": ASK_CONDITION_BASIS,
            "excludedSnapshots": {"byStateAtCollection": {k: excluded[k] for k in sorted(excluded)},
                                  "outsideActivityRange": outside},
            "listings": {"unit": "LISTING_COUNT", "points": listings},
            "quantity": {"unit": "LISTED_QUANTITY", "points": quantity},
            "lowestAsk": {"unit": "USD", "points": lowest}}


def group_series(details: Sequence[Mapping[str, Any]], *, as_of: date, chart_range: Any,
                 roster_denominator: int) -> dict[str, Any]:
    """Sparse daily group series over the FULL roster (no dollar axis).

    A group has no single price, so group series carry counts and quantities
    only. ``provenSpan`` is the intersection of every constituent's proven
    span (null unless all constituents are proven); an absent date is zero
    only inside it. Each point says how many constituents contributed and how
    many were proven on that date.
    """
    out = _series_envelope(as_of, chart_range)
    spans = [(d.get("series") or {}).get("sales", {}).get("provenSpan") for d in details]
    group_span = None
    if details and len(details) == roster_denominator and all(spans):
        start = max(parse_date(s["startDate"]) for s in spans)
        end = min(parse_date(s["endDate"]) for s in spans)
        group_span = _span((start, end)) if start <= end else None
    sales: dict[str, list[int]] = {}
    listings: dict[str, list[int]] = {}
    quantity: dict[str, list[int]] = {}
    for detail in details:
        series = detail.get("series") or {}
        for point in ((series.get("sales") or {}).get("counts") or {}).get("points") or []:
            sales.setdefault(point["date"], []).append(point["observedCount"])
        supply = series.get("supply") or {}
        for point in (supply.get("listings") or {}).get("points") or []:
            listings.setdefault(point["date"], []).append(point["value"])
        for point in (supply.get("quantity") or {}).get("points") or []:
            quantity.setdefault(point["date"], []).append(point["value"])
    count_points = []
    for day in sorted(sales):
        proven_members = sum(_in_span(parse_date(day), s) for s in spans)
        count_points.append({"date": day, "observedCount": sum(sales[day]),
                             "contributingConstituents": len(sales[day]), "provenConstituents": proven_members,
                             "proofState": "PROVEN" if _in_span(parse_date(day), group_span) else "OBSERVED_ONLY"})
    out.update({
        "rosterDenominator": roster_denominator,
        "sales": {"source": SOLD_SOURCE, "conditionBasis": SOLD_CONDITION_BASIS, "tier": "RAW",
                  "provenSpan": group_span, "counts": {"unit": "SALE_COUNT", "points": count_points}},
        "supply": {"source": ASK_SOURCE, "conditionBasis": ASK_CONDITION_BASIS,
                   "aggregation": GROUP_SUPPLY_AGGREGATION,
                   "listings": {"unit": "LISTING_COUNT", "points": [
                       {"date": d, "value": sum(v), "contributingConstituents": len(v)} for d, v in sorted(listings.items())]},
                   "quantity": {"unit": "LISTED_QUANTITY", "points": [
                       {"date": d, "value": sum(v), "contributingConstituents": len(v)} for d, v in sorted(quantity.items())]}},
    })
    return out


# ---------------------------------------------------------------------------
# Assemblers: instrument detail, constituent page, group activity.
# ---------------------------------------------------------------------------
def _versions() -> dict[str, str]:
    return {"contract": CONTRACT_VERSION, "domain": DOMAIN_VERSION, "identity": IDENTITY_RULES_VERSION,
            "grading": GRADING_RULES_VERSION, "qualifierRegistry": QUALIFIER_REGISTRY_VERSION,
            "observation": OBSERVATION_RULES_VERSION, "windowReadiness": WINDOW_READINESS_VERSION,
            "supplyProvenance": SUPPLY_PROVENANCE_VERSION, "series": SERIES_VERSION,
            "tiePolicy": TIE_POLICY_VERSION, "peerPopulation": PEER_POPULATION_VERSION,
            "membership": MEMBERSHIP_CONTRACT_VERSION, "cursor": CURSOR_VERSION}


def _classify_records(records: Sequence[Mapping[str, Any]], *, target_variant: str, target_tier: str,
                      candidates: Sequence[Mapping[str, Any]], candidate_scope: str
                      ) -> tuple[list[dict[str, Any]], dict[str, int]]:
    kept, excluded = dedupe_sold_records(records)
    matched: list[dict[str, Any]] = []
    for row in kept:
        price = money(row.get("price"))
        sold_at = parse_date(row.get("soldAt"))
        ingested = parse_timestamp(row.get("ingestedAt"))
        identity = resolve_exact_identity(attribution=row.get("attribution"),
                                          provider_variant=row.get("providerVariant"),
                                          candidates=candidates, candidate_scope=candidate_scope,
                                          currency=row.get("currency"))
        # Each excluded record is counted once, under its first reason in
        # canonical order, so the counts sum to the excluded record total.
        if not identity.publishable or identity.card_variant_id != target_variant:
            code = (identity.reasons or ("IDENTITY_NO_MATCH",))[0]
            excluded[code] = excluded.get(code, 0) + 1
            continue
        grading = classify_grading(row.get("grader"), row.get("grade"), row.get("gradeQualifier"),
                                   provider_graded_flag=row.get("graded"))
        if not grading.certified_tier:
            code = grading.reasons[0]
            excluded[code] = excluded.get(code, 0) + 1
            continue
        if tier_key(grading) != target_tier:
            excluded["TIER_MISMATCH"] = excluded.get("TIER_MISMATCH", 0) + 1
            continue
        matched.append({"price": price, "soldAt": sold_at, "ingestedAt": ingested})
    ordered = {code: excluded[code] for code in reasons(excluded.keys())}
    return matched, ordered


def _envelope(kind: str, request: Mapping[str, Any], evaluated_at: datetime,
              policy: DisplayPolicy) -> dict[str, Any]:
    return {"kind": kind, "contractVersion": CONTRACT_VERSION, "versions": _versions(),
            "policy": policy.as_contract(), "request": dict(request), "evaluatedAt": iso_utc(evaluated_at),
            "activityGenerationId": None}


def assemble_instrument_detail(inputs: Mapping[str, Any], *, policy: DisplayPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """Build the contract response for one exact instrument (pure)."""
    request = dict(inputs["request"])
    evaluated_at = parse_timestamp(inputs["evaluatedAt"])
    as_of = parse_date(request["asOf"])
    requested_window = int(request.get("windowDays") or 30)
    response: dict[str, Any] = {
        **_envelope("instrumentDetail", request, evaluated_at, policy),
        "instrument": None, "roster": None, "sales": None, "asks": None, "peers": None, "series": None,
    }
    fatal = check_pins(request, inputs)
    parsed: dict[str, Any] | None = None
    if not fatal:
        try:
            parsed = parse_instrument_key(request["instrumentKey"])
        except ValueError:
            fatal = reasons("INVALID_INSTRUMENT_KEY")
    roster = inputs.get("roster") if isinstance(inputs.get("roster"), Mapping) else {}
    if not fatal:
        members = {str(m).lower() for m in roster.get("memberVariantIds") or []}
        if not _is_count(roster.get("denominator")):
            fatal = reasons("ROSTER_INTEGRITY_VIOLATION")
        elif parsed["cardVariantId"] not in members:
            fatal = reasons("INSTRUMENT_NOT_IN_ROSTER")
    if fatal:
        response["availability"] = {"state": "UNAVAILABLE", "reasons": fatal}
        response["capabilities"] = feature_capabilities(fatal=fatal, window=None, identity_ok=False,
                                                        summary=None, peers=None, asks=None)
        response["evidenceFingerprint"] = fingerprint(inputs)
        return response

    activity_generation_id = str(request["activityGenerationId"]).lower()
    response["activityGenerationId"] = activity_generation_id
    grading: GradingIdentity = parsed["grading"]
    response["instrument"] = {"instrumentKey": request["instrumentKey"], "asset": "cards",
                              "cardVariantId": parsed["cardVariantId"],
                              "canonicalCardId": inputs.get("canonicalCardId"),
                              "stream": parsed["stream"], "tier": tier_key(grading),
                              "grading": grading.as_contract()}
    response["roster"] = roster_contract(revision=request["rosterRef"], roster_as_of=roster["asOf"],
                                         roster_denominator=roster["denominator"])

    sold = inputs.get("sold") or {}
    provider_card_id = sold.get("providerCardId")
    records = list(sold.get("records") or [])
    walks = list(sold.get("walks") or [])
    matched, excluded = _classify_records(
        records, target_variant=parsed["cardVariantId"], target_tier=tier_key(grading),
        candidates=sold.get("candidates") or [], candidate_scope=sold.get("candidateScope") or "UNKNOWN")
    observation = sold_observation(records=records, walks=walks, collection_record=sold.get("collectionRecord"),
                                   provider_card_id=provider_card_id)
    observed = observation["state"] == "OBSERVED"
    windows = []
    readiness_by_days: dict[int, WindowReadiness] = {}
    requested_readiness: WindowReadiness | None = None
    requested_summary: dict[str, Any] | None = None
    requested_count: int | None = None
    for days in WINDOW_DAYS:
        start, end = closed_window(as_of, days)
        in_window = [r for r in matched if start <= r["soldAt"] <= end]
        readiness = best_window_readiness(
            walks, window_start=start, window_end=end, grading=grading, evaluated_at=evaluated_at,
            provider_card_id=provider_card_id,
            window_ingested_ats=[r["ingestedAt"] for r in in_window if r["ingestedAt"] is not None],
            policy=policy)
        if readiness.state == "NOT_COLLECTED" and observed:
            # Collection evidence without a completeness receipt: the observed
            # facts stand, the window is simply not proven.
            readiness = WindowReadiness("UNPROVEN", ("COMPLETENESS_RECEIPT_MISSING",), None, False, None)
        readiness_by_days[days] = readiness
        proven_count = len(in_window) if readiness.state == "PROVEN" else None
        summary = None
        if observed:
            summary = {**price_summary([r["price"] for r in in_window], policy=policy),
                       "basis": "PROVEN_WINDOW" if readiness.state == "PROVEN" else "OBSERVED_ONLY"}
        windows.append({"days": days, "startDate": start.isoformat(), "endDate": end.isoformat(),
                        "readiness": readiness.as_contract(),
                        "observedCount": len(in_window) if observed else None,
                        "provenCount": proven_count, "priceSummary": summary})
        if days == requested_window:
            requested_readiness, requested_summary, requested_count = readiness, summary, proven_count
    response["sales"] = {"source": SOLD_SOURCE, "currency": SUPPORTED_CURRENCY,
                         "conditionBasis": SOLD_CONDITION_BASIS, "tier": tier_key(grading),
                         "observation": observation, "windows": windows, "excludedRecordCounts": excluded}

    response["asks"] = (evaluate_supply_snapshot(inputs.get("asks"), evaluated_at=evaluated_at,
                                                 previous_confirmation=inputs.get("previousAskConfirmation"),
                                                 policy=policy)
                        if grading.state == "RAW" else None)

    peers_in = inputs.get("peers")
    if peers_in is not None:
        # Peers must be the same dated window/source/currency/tier, PROVEN
        # coverage and the same scoped cohort revision; an unproven target has
        # no comparable value.
        scope = peer_scope(peers_in.get("scope"), roster_ref=request["rosterRef"],
                           activity_generation_id=activity_generation_id)
        start, end = closed_window(as_of, requested_window)
        key = peer_population_key(window_start=start, window_end=end, source=SOLD_SOURCE,
                                  currency=SUPPORTED_CURRENCY, tier=tier_key(grading), coverage="PROVEN",
                                  scope_key=peer_scope_key(scope))
        response["peers"] = activity_percentile(request["instrumentKey"], requested_count,
                                                peers_in.get("values") or [], population_key=key,
                                                policy=policy, scope=scope)

    series = _series_envelope(as_of, request.get("chartRange"))
    series["sales"] = sales_series(matched, as_of=as_of, observation=observation,
                                   readiness_by_days=readiness_by_days, tier=tier_key(grading))
    series["supply"] = (supply_series(list(inputs.get("askHistory") or []) +
                                      ([inputs["asks"]] if inputs.get("asks") else []),
                                      as_of=as_of, policy=policy)
                        if grading.state == "RAW" else None)
    response["series"] = series

    caps = feature_capabilities(fatal=[], window=requested_readiness, identity_ok=True,
                                summary=requested_summary, peers=response["peers"],
                                asks=response["asks"] or {"state": "NOT_APPLICABLE", "reasons": ["FEATURE_DISABLED_V1"]},
                                observation=observation)
    response["capabilities"] = caps
    # Core features decide AVAILABLE vs PARTIAL. A thin or empty price summary
    # is a legitimate consequence of a proven count, not missing evidence.
    core = ("saleCount", "currentAsks") if grading.state == "RAW" else ("saleCount",)
    if all(caps[name]["available"] for name in core):
        state, why = "AVAILABLE", []
    else:
        state = "PARTIAL"
        why = reasons(*(caps[name]["reasons"] for name in core))
    response["availability"] = {"state": state, "reasons": why}
    response["evidenceFingerprint"] = fingerprint(inputs)
    return response


def _constituent_row(rank: int, detail: Mapping[str, Any], window_days: int) -> dict[str, Any]:
    window = next((w for w in (detail.get("sales") or {}).get("windows") or [] if w["days"] == window_days), None)
    return {
        "rank": rank,
        "instrumentKey": (detail.get("instrument") or {}).get("instrumentKey") or detail["request"]["instrumentKey"],
        "cardVariantId": (detail.get("instrument") or {}).get("cardVariantId"),
        "availability": detail["availability"],
        "observationState": ((detail.get("sales") or {}).get("observation") or {}).get("state") or "NOT_COLLECTED",
        "windowReadiness": window["readiness"]["state"] if window else "NOT_COLLECTED",
        "observedCount": window["observedCount"] if window else None,
        "provenCount": window["provenCount"] if window else None,
        "medianPrice": ((window or {}).get("priceSummary") or {}).get("median"),
        "askState": (detail.get("asks") or {}).get("state"),
        "lowestAsk": (detail.get("asks") or {}).get("lowestAsk"),
        "capabilities": {k: detail["capabilities"][k] for k in ("saleCount", "observedSales", "salePriceSummary",
                                                                "currentAsks")},
    }


def _member_detail(inputs: Mapping[str, Any], member: Mapping[str, Any], member_ids: list[str],
                   window_days: int, policy: DisplayPolicy) -> dict[str, Any]:
    request = inputs["request"]
    return assemble_instrument_detail({
        **member["detailInputs"], "asset": inputs.get("asset"), "servedGenerationId": inputs.get("servedGenerationId"),
        "activityGeneration": inputs.get("activityGeneration"), "evaluatedAt": inputs["evaluatedAt"],
        "roster": {**inputs["roster"], "memberVariantIds": member_ids},
        "request": {"marketKey": request["marketKey"], "activityGenerationId": request["activityGenerationId"],
                    "rosterRef": request["rosterRef"], "instrumentKey": member["instrumentKey"],
                    "asOf": request["asOf"], "windowDays": window_days,
                    "chartRange": request.get("chartRange")}}, policy=policy)


def assemble_constituent_page(inputs: Mapping[str, Any], *, policy: DisplayPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """One pinned, rank-ordered page of per-constituent activity.

    Pins are independent and all validated: activity generation, roster ref,
    and an opaque cursor bound to both (plus market, asOf and window). The UI
    page cap (1..100) applies here only -- never to group aggregation.
    """
    request = dict(inputs["request"])
    limit = request.get("limit") if request.get("limit") is not None else 50
    if not _is_count(limit) or not 1 <= limit <= 100:
        raise ValueError("1 <= limit <= 100 is required")
    window_days = int(request.get("windowDays") or 30)
    evaluated_at = parse_timestamp(inputs["evaluatedAt"])
    response: dict[str, Any] = {**_envelope("constituentActivityPage", request, evaluated_at, policy),
                                "roster": None, "page": None, "rows": []}
    fatal = check_pins(request, inputs)
    roster = inputs.get("roster") if isinstance(inputs.get("roster"), Mapping) else {}
    members: list[dict[str, Any]] = []
    if not fatal:
        members, fatal = validate_members(inputs.get("members"), roster.get("denominator"))
    after_rank = 0
    if not fatal and request.get("cursor") is not None:
        try:
            payload = decode_cursor(request["cursor"])
        except ValueError:
            fatal = reasons("CURSOR_INVALID")
        else:
            if payload != _cursor_payload(request, window_days, payload["k"]):
                fatal = reasons("CURSOR_MISMATCH")
            elif not 1 <= payload["k"] < len(members):
                fatal = reasons("CURSOR_INVALID")
            else:
                after_rank = payload["k"]
    if fatal:
        response["availability"] = {"state": "UNAVAILABLE", "reasons": fatal}
        response["evidenceFingerprint"] = fingerprint(inputs)
        return response
    response["activityGenerationId"] = str(request["activityGenerationId"]).lower()
    response["roster"] = roster_contract(revision=request["rosterRef"], roster_as_of=roster["asOf"],
                                         roster_denominator=roster["denominator"])
    member_ids = [m["cardVariantId"] for m in members]
    selected = [m for m in members if m["rank"] > after_rank][:limit]
    rows = [_constituent_row(m["rank"], _member_detail(inputs, m, member_ids, window_days, policy), window_days)
            for m in selected]
    last = rows[-1]["rank"] if rows else after_rank
    next_cursor = (encode_cursor(_cursor_payload(request, window_days, last))
                   if rows and last < len(members) else None)
    response["rows"] = rows
    response["page"] = {"afterRank": after_rank, "limit": limit, "totalCount": len(members),
                        "nextCursor": next_cursor}
    response["availability"] = {"state": "AVAILABLE", "reasons": []}
    response["evidenceFingerprint"] = fingerprint(inputs)
    return response


def aggregate_group_activity(inputs: Mapping[str, Any], *, policy: DisplayPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """Group-level activity for the focused graph, over the FULL roster.

    The aggregation oracle walks every validated member in rank order; it has
    no page cap. Coverage denominators always use the full roster.
    ``provenSaleCount`` sums only constituents whose window is PROVEN;
    ``observedSaleCountLowerBound`` sums every observed (known-collection)
    count. Missing constituents contribute nothing and are counted, never
    imputed as zero.
    """
    request = dict(inputs["request"])
    window_days = int(request.get("windowDays") or 30)
    evaluated_at = parse_timestamp(inputs["evaluatedAt"])
    response: dict[str, Any] = {**_envelope("groupActivity", request, evaluated_at, policy),
                                "label": MEMBERSHIP_LABEL, "roster": None, "coverage": None, "totals": None,
                                "series": None}
    fatal = check_pins(request, inputs)
    roster = inputs.get("roster") if isinstance(inputs.get("roster"), Mapping) else {}
    members: list[dict[str, Any]] = []
    if not fatal:
        members, fatal = validate_members(inputs.get("members"), roster.get("denominator"))
    if fatal:
        response["availability"] = {"state": "UNAVAILABLE", "reasons": fatal}
        response["evidenceFingerprint"] = fingerprint(inputs)
        return response
    response["activityGenerationId"] = str(request["activityGenerationId"]).lower()
    response["roster"] = roster_contract(revision=request["rosterRef"], roster_as_of=roster["asOf"],
                                         roster_denominator=roster["denominator"])
    member_ids = [m["cardVariantId"] for m in members]
    details = [_member_detail(inputs, m, member_ids, window_days, policy) for m in members]
    rows = [_constituent_row(m["rank"], d, window_days) for m, d in zip(members, details)]
    states = [r["windowReadiness"] for r in rows]
    coverage = {"rosterDenominator": len(members),
                "windowProven": states.count("PROVEN"), "windowPartial": states.count("PARTIAL"),
                "windowUnproven": states.count("UNPROVEN"), "notCollected": states.count("NOT_COLLECTED"),
                "unavailable": sum(r["availability"]["state"] == "UNAVAILABLE" for r in rows)}
    proven = [r["provenCount"] for r in rows if r["windowReadiness"] == "PROVEN"]
    observed = [r["observedCount"] for r in rows if r["observedCount"] is not None]
    response["coverage"] = coverage
    response["totals"] = {"windowDays": window_days,
                          "provenSaleCount": sum(proven) if proven else None,
                          "provenConstituentCount": len(proven),
                          "observedSaleCountLowerBound": sum(observed) if observed else None,
                          "observedConstituentCount": len(observed)}
    response["series"] = group_series(details, as_of=parse_date(request["asOf"]),
                                      chart_range=request.get("chartRange"), roster_denominator=len(members))
    all_proven = coverage["windowProven"] == coverage["rosterDenominator"]
    response["availability"] = {"state": "AVAILABLE" if all_proven else "PARTIAL",
                                "reasons": [] if all_proven else reasons("WINDOW_NOT_PROVEN")}
    response["evidenceFingerprint"] = fingerprint(inputs)
    return response
