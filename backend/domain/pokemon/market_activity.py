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
CONTRACT_VERSION = "market_activity_v1"
DOMAIN_VERSION = "market_activity_domain_v1.0.0"
IDENTITY_RULES_VERSION = "fma_exact_identity_v1"
GRADING_RULES_VERSION = "fma_grading_identity_v1"
WINDOW_READINESS_VERSION = "fma_window_readiness_v1"
SUPPLY_PROVENANCE_VERSION = "fma_supply_provenance_v1"
TIE_POLICY_VERSION = "midrank_v1"
MEMBERSHIP_CONTRACT_VERSION = "fma_membership_v1"

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
    "ROSTER_REVISION_UNSTABLE",
    "QUERY_FINGERPRINT_IS_NOT_A_REVISION",
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
    "SYNC_STATUS_NOT_PROOF",
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
    "ASKS_STALE",
    "EMPTY_WITHOUT_SOURCE_FRESHNESS",
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
def dedupe_sold_records(records: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Keep one row per (source, providerCardId, listingId).

    Identical economic facts (price, currency, soldAt) are duplicates: the
    first-seen row (earliest collectedAt, then input order) is kept. Rows that
    share a listing identity but disagree on those facts are a CONFLICT and
    every copy is excluded -- neither version is silently preferred.
    """
    groups: dict[tuple[str, str, str], list[tuple[int, dict[str, Any]]]] = {}
    for index, row in enumerate(records):
        key = (str(row.get("source") or SOLD_SOURCE), str(row.get("providerCardId")), str(row.get("listingId")))
        groups.setdefault(key, []).append((index, dict(row)))
    kept: list[tuple[int, dict[str, Any]]] = []
    excluded = {"EVIDENCE_DUPLICATE": 0, "EVIDENCE_CONFLICT": 0}
    for items in groups.values():
        facts = {(str(money(r.get("price"))), str(r.get("currency") or "").upper(), str(r.get("soldAt"))[:10])
                 for _, r in items}
        if len(facts) > 1:
            excluded["EVIDENCE_CONFLICT"] += len(items)
            continue
        items.sort(key=lambda pair: (str(pair[1].get("collectedAt") or ""), pair[0]))
        kept.append(items[0])
        excluded["EVIDENCE_DUPLICATE"] += len(items) - 1
    kept.sort(key=lambda pair: pair[0])
    return [row for _, row in kept], {k: v for k, v in excluded.items() if v}


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


def _walk_structure_reasons(walk: Mapping[str, Any]) -> list[str]:
    why: list[str] = []
    if walk.get("sort") != "date_desc":
        why.append("WALK_SORT_NOT_DATE_DESC")
    pages = list(walk.get("pages") or [])
    if not pages:
        return why + ["NOT_COLLECTED"]
    if pages[0].get("inputCursorHash") is not None or not walk.get("startedFromHead"):
        why.append("WALK_HEAD_UNKNOWN")
    filters = {page.get("filterFingerprint") for page in pages}
    if len(filters) != 1 or None in filters or walk.get("filterFingerprint") not in filters:
        why.append("WALK_FILTER_UNSTABLE")
    previous_min: date | None = None
    for index, page in enumerate(pages):
        if index > 0:
            prior = pages[index - 1]
            if (page.get("inputCursorHash") is None
                    or page.get("inputCursorHash") != prior.get("outputCursorHash")
                    or not prior.get("hasMore")):
                why.append("WALK_CURSOR_CHAIN_BROKEN")
        if int(page.get("rowCount") or 0) > 0 and page.get("maxSoldAt") and page.get("minSoldAt"):
            hi, lo = parse_date(page["maxSoldAt"]), parse_date(page["minSoldAt"])
            if lo > hi or (previous_min is not None and hi > previous_min):
                why.append("WALK_NOT_DATE_DESCENDING")
            previous_min = lo
    return why


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
    grading: GradingIdentity, evaluated_at: datetime,
    window_ingested_ats: Sequence[datetime] = (), policy: DisplayPolicy = DEFAULT_POLICY,
) -> WindowReadiness:
    """Readiness of one closed window from one auditable cursor-walk receipt.

    Completeness is proven ONLY by: a date-descending, filter-stable,
    cursor-continuous walk from a known head, reaching strictly beyond the
    window's lower boundary date (or exhausting the stream), plus a completed
    right-edge reconciliation after the window's last day ended. Oldest stored
    date, stored record counts and sync status are not accepted as inputs.
    """
    if not walk:
        return WindowReadiness("NOT_COLLECTED", ("NOT_COLLECTED",), None, False, None)
    structural = _walk_structure_reasons(walk)
    if "NOT_COLLECTED" in structural:
        return WindowReadiness("NOT_COLLECTED", tuple(reasons(structural)), None, False, None)
    stream = _stream_reasons(walk, grading)
    pages = list(walk["pages"])
    exhausted = not pages[-1].get("hasMore")
    rows_pages = [page for page in pages if int(page.get("rowCount") or 0) > 0]
    lowest = parse_date(rows_pages[-1]["minSoldAt"]) if rows_pages else None
    right = walk.get("rightEdge") or {}
    reconciled = parse_timestamp(right.get("reconciledThrough")) if right.get("completed") else None

    fatal = reasons(structural, stream)
    if fatal:
        return WindowReadiness("UNPROVEN", tuple(fatal), None, exhausted, iso_utc(reconciled))

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
        partial.append("RIGHT_EDGE_UNRECONCILED")
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
      whole filtered walk drained (``hasMore`` false). Rows ingested after the
      previous watermark can sit on any later page.
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
    drained = not pages[-1].get("hasMore")
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


def _source_confirmation(offers: Sequence[Mapping[str, Any]], evaluated_at: datetime,
                         policy: DisplayPolicy) -> tuple[datetime | None, list[str], int]:
    """Effective provider confirmation = OLDEST valid per-offer confirmation."""
    why: list[str] = []
    valid: list[datetime] = []
    future_count = 0
    skew = timedelta(seconds=policy.future_timestamp_skew_seconds)
    for offer in offers:
        ts = parse_timestamp(offer.get("providerSnapshotAt"))
        if ts is None:
            why.append("SOURCE_CONFIRMATION_MISSING")
        elif ts > evaluated_at + skew:
            future_count += 1
            why.append("SOURCE_CONFIRMATION_IN_FUTURE")
        else:
            valid.append(ts)
    if len(set(valid)) > 1:
        why.append("SOURCE_CONFIRMATION_MIXED")
    return (min(valid) if valid else None), why, future_count


def evaluate_supply_snapshot(snapshot: Mapping[str, Any] | None, *, evaluated_at: datetime,
                             previous_confirmation: Any = None,
                             policy: DisplayPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """Current-ask readiness from PROVIDER confirmation only.

    ``observedAt`` (local collection time) and ``listingUpdatedAt`` are
    carried as labelled facts but never establish freshness. An empty offer
    list proves zero current inventory only when the provider supplied its own
    source freshness (``sourceConfirmedAt``) for that empty result.
    """
    base = {"source": ASK_SOURCE, "conditionBasis": ASK_CONDITION_BASIS, "providerConfirmedAt": None,
            "confirmationAgeHours": None, "collectedAt": None, "capturedListingCount": None,
            "capturedQuantity": None, "depth": None, "lowestAsk": None}
    if not snapshot:
        return {**base, "state": "NOT_COLLECTED", "reasons": reasons("NOT_COLLECTED")}
    base["collectedAt"] = iso_utc(parse_timestamp(snapshot.get("observedAt")))
    if snapshot.get("observationState") != "OBSERVED":
        return {**base, "state": "COLLECTION_FAILED", "reasons": reasons("SUPPLY_COLLECTION_FAILED")}
    offers = list(snapshot.get("offers") or [])
    truncated = bool(snapshot.get("hasMore"))
    why: list[str] = ["DEPTH_TRUNCATED"] if truncated else []
    base["depth"] = "LOWER_BOUND" if truncated else "COMPLETE_AT_SOURCE"

    if not offers:
        confirmed = parse_timestamp(snapshot.get("sourceConfirmedAt"))
        base.update(capturedListingCount=0, capturedQuantity={"value": 0, "provenance": PROVENANCE_EXPLICIT})
        if confirmed is None:
            return {**base, "capturedQuantity": None, "capturedListingCount": None, "depth": None,
                    "state": "ZERO_UNPROVEN", "reasons": reasons(why, "EMPTY_WITHOUT_SOURCE_FRESHNESS")}
        if confirmed > evaluated_at + timedelta(seconds=policy.future_timestamp_skew_seconds):
            return {**base, "capturedQuantity": None, "capturedListingCount": None, "depth": None,
                    "state": "CONFIRMATION_INVALID", "reasons": reasons(why, "SOURCE_CONFIRMATION_IN_FUTURE")}
        age = evaluated_at - confirmed
        base.update(providerConfirmedAt=iso_utc(confirmed), confirmationAgeHours=_hours(age))
        if age > timedelta(hours=policy.ask_confirmation_max_age_hours):
            return {**base, "state": "STALE", "reasons": reasons(why, "ASKS_STALE")}
        return {**base, "state": "ZERO_PROVEN", "reasons": reasons(why)}

    confirmed, confirmation_reasons, future = _source_confirmation(offers, evaluated_at, policy)
    why.extend(confirmation_reasons)
    usable = [o for o in offers if (ts := parse_timestamp(o.get("providerSnapshotAt"))) is None
              or ts <= evaluated_at + timedelta(seconds=policy.future_timestamp_skew_seconds)]
    provenance = [(money(o["itemPrice"]), o) for o in usable]
    shipping_states = {o.get("shippingProvenance") or PROVENANCE_LEGACY for _, o in provenance}
    quantity_states = {o.get("quantityProvenance") or PROVENANCE_LEGACY for _, o in provenance}
    if PROVENANCE_UNKNOWN in shipping_states:
        why.append("SHIPPING_UNKNOWN")
    if PROVENANCE_LEGACY in shipping_states:
        why.append("SHIPPING_LEGACY_UNVERIFIED")
    if PROVENANCE_DEFAULTED in quantity_states:
        why.append("QUANTITY_DEFAULTED")
    if PROVENANCE_LEGACY in quantity_states:
        why.append("QUANTITY_LEGACY_UNVERIFIED")

    base["capturedListingCount"] = len(usable)
    quantity_prov = ("PROVEN" if quantity_states == {PROVENANCE_EXPLICIT}
                     else PROVENANCE_LEGACY if PROVENANCE_LEGACY in quantity_states
                     else "DEFAULTED_LOWER_BOUND")
    base["capturedQuantity"] = {"value": sum(int(o.get("quantity") or 1) for _, o in provenance),
                                "provenance": quantity_prov}
    if provenance:
        if shipping_states == {PROVENANCE_EXPLICIT}:
            landed = min(price + money(o["shippingPrice"]) for price, o in provenance)
            base["lowestAsk"] = {"basis": "LANDED_PROVEN", "price": money_json(landed)}
        else:
            basis = "ITEM_ONLY_LEGACY_UNVERIFIED" if PROVENANCE_LEGACY in shipping_states else "ITEM_ONLY"
            base["lowestAsk"] = {"basis": basis, "price": money_json(min(p for p, _ in provenance))}

    if confirmed is None:
        state = "CONFIRMATION_INVALID" if future else "CONFIRMATION_MISSING"
        return {**base, "state": state, "reasons": reasons(why)}
    previous = parse_timestamp(previous_confirmation)
    if previous is not None and previous == confirmed:
        why.append("SOURCE_CONFIRMATION_REPEATED")
    age = evaluated_at - confirmed
    base.update(providerConfirmedAt=iso_utc(confirmed), confirmationAgeHours=_hours(age))
    if age > timedelta(hours=policy.ask_confirmation_max_age_hours):
        return {**base, "state": "STALE", "reasons": reasons(why, "ASKS_STALE")}
    return {**base, "state": "FRESH", "reasons": reasons(why)}


def _hours(delta: timedelta) -> str:
    return str((Decimal(int(delta.total_seconds())) / Decimal(3600)).quantize(Decimal("0.1"), rounding=ROUND_HALF_EVEN))


# ---------------------------------------------------------------------------
# 6. Group membership (CURRENT_ROSTER_RETROSPECTIVE).
# ---------------------------------------------------------------------------
REVISION_KINDS = ("SURFACE_V2_GENERATION", "QUERY_CACHE_PUBLISHED_REVISION", "QUERY_CACHE_FINGERPRINT")


def validate_roster_revision(revision: Mapping[str, Any] | None) -> list[str]:
    """A roster revision must name an immutable published snapshot.

    * SURFACE_V2_GENERATION: generation_id + market_key; the V2 constituents
      table is keyed by (generation_id, market_key, rank) and a generation is
      never mutated after promotion.
    * QUERY_CACHE_PUBLISHED_REVISION: the FMA-1 sidecar (see
      SCHEMA_DECISION.md) -- fingerprint + immutable revision id + computedThrough.
    * A bare query fingerprint is a SPECIFICATION: the custom cache row and its
      constituent detail are replaced in place on rebuild, so pages read across
      a rebuild can mix rosters. It is rejected.
    """
    if not revision:
        return reasons("ROSTER_REVISION_UNSTABLE")
    kind = revision.get("kind")
    if kind == "SURFACE_V2_GENERATION":
        ok = bool(_UUID.match(str(revision.get("generationId") or "").lower())) and bool(revision.get("marketKey"))
        return [] if ok else reasons("ROSTER_REVISION_UNSTABLE")
    if kind == "QUERY_CACHE_PUBLISHED_REVISION":
        ok = all(revision.get(k) for k in ("queryFingerprint", "revisionId", "computedThrough"))
        return [] if ok else reasons("ROSTER_REVISION_UNSTABLE")
    if kind == "QUERY_CACHE_FINGERPRINT":
        return reasons("QUERY_FINGERPRINT_IS_NOT_A_REVISION", "ROSTER_REVISION_UNSTABLE")
    return reasons("ROSTER_REVISION_UNSTABLE")


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


# ---------------------------------------------------------------------------
# 7. Metrics and peers.
# ---------------------------------------------------------------------------
def price_summary(prices: Sequence[Any], *, policy: DisplayPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """Median/low/high of ONE exact tier. Raw and graded never share a call."""
    values = sorted(money(p) for p in prices)
    out = {"recordCount": len(values), "median": None, "low": None, "high": None}
    if not values:
        return {**out, "state": "NO_RECORDS", "reasons": reasons("NO_RECORDS")}
    if len(values) < policy.price_summary_min_records:
        return {**out, "state": "THIN", "reasons": reasons("THIN_RECORDS")}
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
    return {**out, "state": "AVAILABLE", "reasons": [],
            "median": money_json(median.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)),
            "low": money_json(values[0]), "high": money_json(values[-1])}


def peer_population_key(*, window_days: int, source: str, currency: str, tier: str, coverage: str) -> str:
    return f"{int(window_days)}d|{source}|{currency}|{tier}|{coverage}"


def activity_percentile(target_key: str, target_value: int | None, peers: Sequence[Mapping[str, Any]], *,
                        population_key: str, policy: DisplayPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """Midrank "Activity percentile" against OTHER eligible peers.

    * peers must share the exact population key (window, source, currency,
      tier, coverage); the target is excluded from the denominator;
    * midrank = (strictly-below + 0.5 * ties) / N; the literal
      ``strictBelowPct`` counts strictly-below only, never half the ties;
    * thin (N < policy), all-zero and all-tied populations are explicit states.
    """
    others = [p for p in peers if p.get("instrumentKey") != target_key
              and p.get("populationKey") == population_key and p.get("value") is not None]
    n = len(others)
    out = {"label": PERCENTILE_LABEL, "tiePolicy": TIE_POLICY_VERSION, "populationKey": population_key,
           "eligibleOtherPeerCount": n, "activityPercentile": None, "strictBelowPct": None,
           "tieCount": None, "scopeLabel": RESEARCH_PANEL_SCOPE_LABEL, "claimsAllPokemon": False}
    if target_value is None:
        return {**out, "state": "UNAVAILABLE", "reasons": reasons("WINDOW_NOT_PROVEN")}
    if n == 0:
        return {**out, "state": "NO_PEERS", "reasons": reasons("NO_PEERS")}
    values = [int(p["value"]) for p in others]
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


def population_scope(panel_id: str) -> dict[str, Any]:
    if panel_id != RESEARCH_PANEL_ID:
        raise ValueError("V1 peers are defined only on the frozen research panel")
    return {"panelId": RESEARCH_PANEL_ID, "scopeLabel": RESEARCH_PANEL_SCOPE_LABEL, "claimsAllPokemon": False}


# ---------------------------------------------------------------------------
# Per-feature capabilities and independent availability dimensions.
# ---------------------------------------------------------------------------
FEATURES = ("saleCount", "salePriceSummary", "activityPercentile", "currentAsks",
            "askDepth", "landedAsk", "supplyTurnover", "inferredSalesFromListings")


def feature_capabilities(*, fatal: Sequence[str], window: WindowReadiness | None,
                         identity_ok: bool, summary: Mapping[str, Any] | None,
                         peers: Mapping[str, Any] | None, asks: Mapping[str, Any] | None) -> dict[str, Any]:
    def cap(ok: bool, why: Iterable[str]) -> dict[str, Any]:
        return {"available": bool(ok), "reasons": [] if ok else reasons(why)}

    if fatal:
        caps = {name: cap(False, fatal) for name in FEATURES}
    else:
        window_ok = bool(window and window.state == "PROVEN" and identity_ok)
        if window is None:
            window_why = ["NOT_COLLECTED"]
        elif window.state == "NOT_COLLECTED":
            window_why = list(window.reasons)
        else:
            window_why = list(window.reasons) + ["WINDOW_NOT_PROVEN"]
        caps = {"saleCount": cap(window_ok, window_why)}
        s_ok = window_ok and bool(summary) and summary.get("state") == "AVAILABLE"
        caps["salePriceSummary"] = cap(s_ok, window_why if not window_ok else (summary or {}).get("reasons") or [])
        p_ok = window_ok and bool(peers) and peers.get("state") == "AVAILABLE"
        caps["activityPercentile"] = cap(p_ok, window_why if not window_ok else (peers or {}).get("reasons") or [])
        a_state = (asks or {}).get("state")
        a_why = (asks or {}).get("reasons") or ["NOT_COLLECTED"]
        caps["currentAsks"] = cap(a_state in {"FRESH", "ZERO_PROVEN"}, a_why)
        caps["askDepth"] = cap(a_state in {"FRESH", "ZERO_PROVEN"}, a_why)
        landed = a_state == "FRESH" and ((asks or {}).get("lowestAsk") or {}).get("basis") == "LANDED_PROVEN"
        caps["landedAsk"] = cap(landed, [c for c in a_why if c != "DEPTH_TRUNCATED"] or ["SHIPPING_UNKNOWN"])
        caps["supplyTurnover"] = cap(False, ["FEATURE_DISABLED_V1"])
        caps["inferredSalesFromListings"] = cap(False, ["FEATURE_DISABLED_V1"])
    return caps


# ---------------------------------------------------------------------------
# Assemblers: instrument detail, constituent page, group activity.
# ---------------------------------------------------------------------------
def _versions() -> dict[str, str]:
    return {"contract": CONTRACT_VERSION, "domain": DOMAIN_VERSION, "identity": IDENTITY_RULES_VERSION,
            "grading": GRADING_RULES_VERSION, "qualifierRegistry": QUALIFIER_REGISTRY_VERSION,
            "windowReadiness": WINDOW_READINESS_VERSION, "supplyProvenance": SUPPLY_PROVENANCE_VERSION,
            "tiePolicy": TIE_POLICY_VERSION, "membership": MEMBERSHIP_CONTRACT_VERSION}


def _classify_records(records: Sequence[Mapping[str, Any]], *, target_variant: str, target_tier: str,
                      candidates: Sequence[Mapping[str, Any]], candidate_scope: str
                      ) -> tuple[list[dict[str, Any]], dict[str, int]]:
    kept, excluded = dedupe_sold_records(records)
    matched: list[dict[str, Any]] = []
    for row in kept:
        try:
            price = money(row.get("price"))
            sold_at = parse_date(row.get("soldAt"))
            ingested = parse_timestamp(row.get("ingestedAt"))
        except ValueError:
            excluded["INVALID_EVIDENCE_ROW"] = excluded.get("INVALID_EVIDENCE_ROW", 0) + 1
            continue
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


def assemble_instrument_detail(inputs: Mapping[str, Any], *, policy: DisplayPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """Build the contract response for one exact instrument (pure)."""
    request = dict(inputs["request"])
    evaluated_at = parse_timestamp(inputs["evaluatedAt"])
    as_of = parse_date(request["asOf"])
    requested_window = int(request.get("windowDays") or 30)
    response: dict[str, Any] = {
        "kind": "instrumentDetail", "contractVersion": CONTRACT_VERSION, "versions": _versions(),
        "policy": policy.as_contract(), "request": request, "evaluatedAt": iso_utc(evaluated_at),
        "instrument": None, "roster": None, "sales": None, "asks": None, "peers": None,
    }
    fatal = reasons(check_asset(inputs.get("asset")),
                    check_generation(request.get("generationId"), inputs.get("servedGenerationId")))
    parsed: dict[str, Any] | None = None
    if not fatal:
        try:
            parsed = parse_instrument_key(request["instrumentKey"])
        except ValueError:
            fatal = reasons("INVALID_INSTRUMENT_KEY")
    roster = inputs.get("roster")
    if not fatal:
        roster_why = validate_roster_revision((roster or {}).get("revision"))
        members = {str(m).lower() for m in (roster or {}).get("memberVariantIds") or []}
        if not roster_why and parsed["cardVariantId"] not in members:
            roster_why = reasons("INSTRUMENT_NOT_IN_ROSTER")
        fatal = roster_why
    if fatal:
        response["availability"] = {"state": "UNAVAILABLE", "reasons": fatal}
        response["capabilities"] = feature_capabilities(fatal=fatal, window=None, identity_ok=False,
                                                        summary=None, peers=None, asks=None)
        response["evidenceFingerprint"] = fingerprint(inputs)
        return response

    grading: GradingIdentity = parsed["grading"]
    response["instrument"] = {"instrumentKey": request["instrumentKey"], "asset": "cards",
                              "cardVariantId": parsed["cardVariantId"],
                              "canonicalCardId": inputs.get("canonicalCardId"),
                              "stream": parsed["stream"], "tier": tier_key(grading),
                              "grading": grading.as_contract()}
    response["roster"] = roster_contract(revision=roster["revision"], roster_as_of=roster["asOf"],
                                         roster_denominator=roster["denominator"])

    sold = inputs.get("sold") or {}
    matched, excluded = _classify_records(
        sold.get("records") or [], target_variant=parsed["cardVariantId"], target_tier=tier_key(grading),
        candidates=sold.get("candidates") or [], candidate_scope=sold.get("candidateScope") or "UNKNOWN")
    walks = list(sold.get("walks") or [])
    windows = []
    requested_readiness: WindowReadiness | None = None
    requested_summary: dict[str, Any] | None = None
    requested_count: int | None = None
    for days in WINDOW_DAYS:
        start, end = closed_window(as_of, days)
        in_window = [r for r in matched if start <= r["soldAt"] <= end]
        readiness = best_window_readiness(
            walks, window_start=start, window_end=end, grading=grading, evaluated_at=evaluated_at,
            window_ingested_ats=[r["ingestedAt"] for r in in_window if r["ingestedAt"] is not None],
            policy=policy)
        collected = readiness.state != "NOT_COLLECTED"
        proven_count = len(in_window) if readiness.state == "PROVEN" else None
        summary = price_summary([r["price"] for r in in_window], policy=policy) if collected else None
        windows.append({"days": days, "startDate": start.isoformat(), "endDate": end.isoformat(),
                        "readiness": readiness.as_contract(),
                        "observedCount": len(in_window) if collected else None,
                        "provenCount": proven_count, "priceSummary": summary})
        if days == requested_window:
            requested_readiness, requested_summary, requested_count = readiness, summary, proven_count
    response["sales"] = {"source": SOLD_SOURCE, "currency": SUPPORTED_CURRENCY,
                         "conditionBasis": SOLD_CONDITION_BASIS, "tier": tier_key(grading),
                         "windows": windows, "excludedRecordCounts": excluded}

    response["asks"] = (evaluate_supply_snapshot(inputs.get("asks"), evaluated_at=evaluated_at,
                                                 previous_confirmation=inputs.get("previousAskConfirmation"),
                                                 policy=policy)
                        if grading.state == "RAW" else None)

    peers_in = inputs.get("peers")
    if peers_in is not None:
        # Peers must be same window/source/currency/tier AND proven coverage;
        # an unproven target has no comparable value.
        key = peer_population_key(window_days=requested_window, source=SOLD_SOURCE,
                                  currency=SUPPORTED_CURRENCY, tier=tier_key(grading), coverage="PROVEN")
        population_scope(peers_in.get("panelId"))
        response["peers"] = activity_percentile(request["instrumentKey"], requested_count,
                                                peers_in.get("values") or [], population_key=key, policy=policy)

    caps = feature_capabilities(fatal=[], window=requested_readiness, identity_ok=True,
                                summary=requested_summary, peers=response["peers"],
                                asks=response["asks"] or {"state": "NOT_APPLICABLE", "reasons": ["FEATURE_DISABLED_V1"]})
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
        "windowReadiness": window["readiness"]["state"] if window else "NOT_COLLECTED",
        "observedCount": window["observedCount"] if window else None,
        "provenCount": window["provenCount"] if window else None,
        "medianPrice": ((window or {}).get("priceSummary") or {}).get("median"),
        "askState": (detail.get("asks") or {}).get("state"),
        "lowestAsk": (detail.get("asks") or {}).get("lowestAsk"),
        "capabilities": {k: detail["capabilities"][k] for k in ("saleCount", "salePriceSummary", "currentAsks")},
    }


def assemble_constituent_page(inputs: Mapping[str, Any], *, policy: DisplayPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """One generation-pinned, rank-ordered page of per-constituent activity."""
    request = dict(inputs["request"])
    after_rank, limit = int(request.get("afterRank") or 0), int(request.get("limit") or 50)
    if after_rank < 0 or not 1 <= limit <= 100:
        raise ValueError("afterRank >= 0 and 1 <= limit <= 100 are required")
    window_days = int(request.get("windowDays") or 30)
    fatal = reasons(check_asset(inputs.get("asset")),
                    check_generation(request.get("generationId"), inputs.get("servedGenerationId")),
                    validate_roster_revision((inputs.get("roster") or {}).get("revision")))
    response: dict[str, Any] = {"kind": "constituentActivityPage", "contractVersion": CONTRACT_VERSION,
                                "versions": _versions(), "policy": policy.as_contract(), "request": request,
                                "evaluatedAt": iso_utc(parse_timestamp(inputs["evaluatedAt"])),
                                "roster": None, "page": None, "rows": []}
    if fatal:
        response["availability"] = {"state": "UNAVAILABLE", "reasons": fatal}
        response["evidenceFingerprint"] = fingerprint(inputs)
        return response
    roster = inputs["roster"]
    members = list(inputs.get("members") or [])
    response["roster"] = roster_contract(revision=roster["revision"], roster_as_of=roster["asOf"],
                                         roster_denominator=roster["denominator"])
    if len(members) != int(roster["denominator"]):
        raise ValueError("member list must equal the full roster denominator")
    selected = [m for m in members if int(m["rank"]) > after_rank][:limit]
    rows = []
    for member in selected:
        detail = assemble_instrument_detail({
            **member["detailInputs"], "asset": inputs["asset"], "servedGenerationId": inputs["servedGenerationId"],
            "evaluatedAt": inputs["evaluatedAt"],
            "roster": {**roster, "memberVariantIds": [m["cardVariantId"] for m in members]},
            "request": {"marketKey": request["marketKey"], "generationId": request["generationId"],
                        "instrumentKey": member["instrumentKey"], "asOf": request["asOf"],
                        "windowDays": window_days}}, policy=policy)
        rows.append(_constituent_row(int(member["rank"]), detail, window_days))
    last = rows[-1]["rank"] if rows else after_rank
    response["rows"] = rows
    response["page"] = {"afterRank": after_rank, "limit": limit, "totalCount": int(roster["denominator"]),
                        "nextCursor": last if rows and last < int(roster["denominator"]) else None}
    response["availability"] = {"state": "AVAILABLE", "reasons": []}
    response["evidenceFingerprint"] = fingerprint(inputs)
    return response


def aggregate_group_activity(inputs: Mapping[str, Any], *, policy: DisplayPolicy = DEFAULT_POLICY) -> dict[str, Any]:
    """Group-level activity for the focused graph, over the FULL roster.

    Coverage denominators always use the full roster. ``provenSaleCount`` sums
    only constituents whose window is PROVEN; ``observedSaleCountLowerBound``
    is a labelled lower bound over every collected window. Missing
    constituents contribute nothing and are counted, never imputed as zero.
    """
    page = assemble_constituent_page({**inputs, "request": {**inputs["request"], "afterRank": 0, "limit": 100}},
                                     policy=policy)
    request = dict(inputs["request"])
    response: dict[str, Any] = {"kind": "groupActivity", "contractVersion": CONTRACT_VERSION,
                                "versions": _versions(), "policy": policy.as_contract(), "request": request,
                                "evaluatedAt": page["evaluatedAt"], "label": MEMBERSHIP_LABEL,
                                "roster": page["roster"], "coverage": None, "totals": None,
                                "availability": page["availability"]}
    if page["availability"]["state"] == "UNAVAILABLE":
        response["evidenceFingerprint"] = fingerprint(inputs)
        return response
    if page["page"]["nextCursor"] is not None:
        raise ValueError("group aggregation requires the full roster (<=100 members in V1 fixtures)")
    rows = page["rows"]
    states = [r["windowReadiness"] for r in rows]
    coverage = {"rosterDenominator": page["roster"]["rosterDenominator"],
                "windowProven": states.count("PROVEN"), "windowPartial": states.count("PARTIAL"),
                "windowUnproven": states.count("UNPROVEN"), "notCollected": states.count("NOT_COLLECTED"),
                "unavailable": sum(r["availability"]["state"] == "UNAVAILABLE" for r in rows)}
    proven = [r["provenCount"] for r in rows if r["windowReadiness"] == "PROVEN"]
    # Every collected observation is a valid lower bound, whatever its proof.
    observed = [r["observedCount"] for r in rows if r["windowReadiness"] in {"PROVEN", "PARTIAL", "UNPROVEN"}]
    response["coverage"] = coverage
    response["totals"] = {"windowDays": int(request.get("windowDays") or 30),
                          "provenSaleCount": sum(proven) if proven else None,
                          "provenConstituentCount": len(proven),
                          "observedSaleCountLowerBound": sum(observed) if observed else None,
                          "observedConstituentCount": len(observed)}
    all_proven = coverage["windowProven"] == coverage["rosterDenominator"]
    response["availability"] = {"state": "AVAILABLE" if all_proven else "PARTIAL",
                                "reasons": [] if all_proven else reasons("WINDOW_NOT_PROVEN")}
    response["evidenceFingerprint"] = fingerprint(inputs)
    return response
