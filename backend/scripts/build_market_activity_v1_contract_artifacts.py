"""Regenerate the Focused Market Activity V1 schemas, fixtures and manifest.

Offline and pure: no provider calls, no database connection, no network.
Fixture ``expected`` blocks are produced by the domain assemblers and then
frozen; ``test_market_activity_contract.py`` fails if the committed artifacts
drift from this generator or from the domain rules.

    python -m backend.scripts.build_market_activity_v1_contract_artifacts --write
    python -m backend.scripts.build_market_activity_v1_contract_artifacts --check
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from backend.domain.pokemon import market_activity as ma
from backend.domain.pokemon.market_activity_contract import SchemaRegistry, content_fingerprint

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "research" / "market_activity_v1"
CONTRACTS = OUT / "contracts"
FIXTURES = OUT / "fixtures"
# FMA-0.1: fixture set 2 (contract market_activity_v1.1). Set 1 is superseded.
FIXTURE_SET_VERSION = "market_activity_v1_fixtures_2"

UUID_PATTERN = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
KEY_PATTERN = (r"^card:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:"
               r"(raw|graded:[A-Z]+:[A-Za-z0-9.%]+:[A-Za-z0-9.%-]+)$")
CURSOR_PATTERN = r"^fmac1\.[0-9a-f]+\.[0-9a-f]{16}$"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"common.schema.json#/$defs/{name}"}


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def _obj(props: dict[str, Any], required: list[str] | None = None, *, extra: bool = False) -> dict[str, Any]:
    return {"type": "object", "properties": props,
            "required": list(props) if required is None else required, "additionalProperties": extra}


def _axis(unit: str, point_def: str) -> dict[str, Any]:
    """One unit axis: dollars, counts and quantities never share an axis."""
    return _obj({"unit": {"const": unit}, "points": {"type": "array", "items": {"$ref": f"#/$defs/{point_def}"}}})


def common_schema() -> dict[str, Any]:
    reason_list = {"type": "array", "items": {"$ref": "#/$defs/ReasonCode"}}
    capability = _obj({"available": {"type": "boolean"}, "reasons": {"$ref": "#/$defs/ReasonList"}})
    expiring = _obj({"available": {"type": "boolean"}, "reasons": {"$ref": "#/$defs/ReasonList"},
                     "expiresAt": {"$ref": "#/$defs/NullableDateTime"}})
    money_schema = _obj({"amount": {"type": "string", "pattern": r"^\d+\.\d{2}$"},
                         "currency": {"const": "USD"}})
    count = {"type": "integer", "minimum": 0}
    positive = {"type": "integer", "minimum": 1}
    date_ref, dt_ref = {"$ref": "#/$defs/Date"}, {"$ref": "#/$defs/DateTime"}
    series_envelope = {
        "version": {"const": ma.SERIES_VERSION}, "storage": {"const": ma.SERIES_STORAGE}, "asOf": date_ref,
        "zeroRule": {"const": ma.SERIES_ZERO_RULE},
        "outsideActivityRange": {"const": ma.SERIES_OUTSIDE_ACTIVITY_RANGE},
        "canonicalRange": {"$ref": "#/$defs/NullableDateRange"}, "activityRange": {"$ref": "#/$defs/DateRange"},
    }
    ask_depth = {"enum": ["LOWER_BOUND", "COMPLETE_AT_SOURCE", "UNKNOWN", None]}
    quantity_provenance = {"enum": ["PROVEN", "EXPLICIT", "DEFAULTED_LOWER_BOUND", "LEGACY_UNVERIFIED"]}
    defs = {
        "ReasonCode": {"type": "string", "enum": list(ma.REASON_CODES)},
        "ReasonList": reason_list,
        "Uuid": {"type": "string", "pattern": UUID_PATTERN},
        "Date": {"type": "string", "format": "date"},
        "DateTime": {"type": "string", "format": "date-time"},
        "NullableDateTime": _nullable({"$ref": "#/$defs/DateTime"}),
        "DateRange": _obj({"startDate": date_ref, "endDate": date_ref}),
        "NullableDateRange": _nullable({"$ref": "#/$defs/DateRange"}),
        "Money": money_schema,
        "NullableMoney": _nullable({"$ref": "#/$defs/Money"}),
        "DecimalString": {"type": "string", "pattern": r"^-?\d+\.\d$"},
        "WindowDays": {"type": "integer", "enum": list(ma.WINDOW_DAYS)},
        "InstrumentKey": {"type": "string", "pattern": KEY_PATTERN},
        "Cursor": {"type": "string", "pattern": CURSOR_PATTERN},
        "Availability": _obj({"state": {"enum": ["AVAILABLE", "PARTIAL", "UNAVAILABLE"]},
                              "reasons": {"$ref": "#/$defs/ReasonList"}}),
        "Versions": _obj({k: {"type": "string"} for k in ma._versions()}),
        "Policy": _obj({"version": {"type": "string"},
                        "askConfirmationMaxAgeHours": {"type": "integer", "minimum": 1},
                        "soldHeadReceiptMaxAgeHours": {"type": "integer", "minimum": 1},
                        "priceSummaryMinRecords": {"type": "integer", "minimum": 1},
                        "percentileMinOtherPeers": {"type": "integer", "minimum": 1},
                        "futureTimestampSkewSeconds": {"type": "integer", "minimum": 0},
                        "tiePolicy": {"const": ma.TIE_POLICY_VERSION}}),
        # rosterRef: the immutable roster (prepared V2 generation or custom
        # published revision). A bare query fingerprint is not accepted.
        "RosterRevision": {"oneOf": [
            _obj({"kind": {"const": "SURFACE_V2_GENERATION"}, "generationId": {"$ref": "#/$defs/Uuid"},
                  "marketKey": {"type": "string", "minLength": 1}}),
            _obj({"kind": {"const": "QUERY_CACHE_PUBLISHED_REVISION"},
                  "queryFingerprint": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                  "revisionId": {"$ref": "#/$defs/Uuid"}, "computedThrough": {"$ref": "#/$defs/Date"}}),
        ]},
        "Roster": _nullable(_obj({
            "membershipMode": {"const": ma.MEMBERSHIP_MODE}, "label": {"const": ma.MEMBERSHIP_LABEL},
            "membershipContractVersion": {"const": ma.MEMBERSHIP_CONTRACT_VERSION},
            "rosterAsOf": {"$ref": "#/$defs/Date"}, "rosterRevision": {"$ref": "#/$defs/RosterRevision"},
            "rosterDenominator": {"type": "integer", "minimum": 0}})),
        "Capability": capability,
        "ExpiringCapability": expiring,
        "Capabilities": _obj({name: {"$ref": "#/$defs/ExpiringCapability" if name in ma.EXPIRING_FEATURES
                                     else "#/$defs/Capability"} for name in ma.FEATURES}),
        "Grading": _obj({"state": {"enum": ["RAW", "GRADED", "GRADED_QUALIFIED", "INCOMPLETE", "UNRECOGNIZED"]},
                         "grader": {"type": ["string", "null"]}, "grade": {"type": ["string", "null"]},
                         "qualifier": {"type": ["string", "null"]}, "reasons": {"$ref": "#/$defs/ReasonList"}}),
        "Observation": _obj({"state": {"enum": ["OBSERVED", "NOT_COLLECTED"]},
                             "basis": {"enum": list(ma.OBSERVATION_BASES) + [None]},
                             "reasons": {"$ref": "#/$defs/ReasonList"}}),
        "WindowReadiness": _obj({"state": {"enum": list(ma.READINESS_ORDER)},
                                 "reasons": {"$ref": "#/$defs/ReasonList"},
                                 "provenLowerBoundDate": _nullable({"$ref": "#/$defs/Date"}),
                                 "exhausted": {"type": "boolean"},
                                 "reconciledThrough": _nullable({"$ref": "#/$defs/DateTime"})}),
        "PriceSummary": _nullable(_obj({"state": {"enum": ["AVAILABLE", "THIN", "NO_RECORDS"]},
                                        "basis": {"enum": ["PROVEN_WINDOW", "OBSERVED_ONLY"]},
                                        "reasons": {"$ref": "#/$defs/ReasonList"},
                                        "recordCount": {"type": "integer", "minimum": 0},
                                        "median": {"$ref": "#/$defs/NullableMoney"},
                                        "low": {"$ref": "#/$defs/NullableMoney"},
                                        "high": {"$ref": "#/$defs/NullableMoney"}})),
        "NullableCount": {"type": ["integer", "null"], "minimum": 0},
        "SalesWindow": _obj({"days": {"$ref": "#/$defs/WindowDays"}, "startDate": {"$ref": "#/$defs/Date"},
                             "endDate": {"$ref": "#/$defs/Date"}, "readiness": {"$ref": "#/$defs/WindowReadiness"},
                             "observedCount": {"$ref": "#/$defs/NullableCount"},
                             "provenCount": {"$ref": "#/$defs/NullableCount"},
                             "priceSummary": {"$ref": "#/$defs/PriceSummary"}}),
        "LowestAskBasis": {"enum": ["LANDED_PROVEN", "ITEM_ONLY", "ITEM_ONLY_LEGACY_UNVERIFIED"]},
        "LowestAsk": _nullable(_obj({"basis": {"$ref": "#/$defs/LowestAskBasis"},
                                     "price": {"$ref": "#/$defs/Money"}})),
        "AskState": {"enum": ["NOT_COLLECTED", "COLLECTION_FAILED", "CONFIRMATION_MISSING",
                              "CONFIRMATION_INVALID", "STALE", "PARTIALLY_CONFIRMED", "FRESH", "ZERO_PROVEN",
                              "ZERO_UNPROVEN"]},
        "CapturedQuantity": _obj({"value": count, "provenance": quantity_provenance}),
        "Asks": _nullable(_obj({
            "source": {"const": ma.ASK_SOURCE}, "conditionBasis": {"const": ma.ASK_CONDITION_BASIS},
            "state": {"$ref": "#/$defs/AskState"}, "reasons": {"$ref": "#/$defs/ReasonList"},
            "providerConfirmedAt": _nullable({"$ref": "#/$defs/DateTime"}),
            "confirmationAgeHours": _nullable({"$ref": "#/$defs/DecimalString"}),
            "currentUntil": {"$ref": "#/$defs/NullableDateTime"},
            "collectedAt": _nullable({"$ref": "#/$defs/DateTime"}),
            "offerQualification": {"enum": ["CURRENT", "NOT_CURRENT"]},
            "capturedListingCount": {"$ref": "#/$defs/NullableCount"},
            "capturedQuantity": _nullable({"$ref": "#/$defs/CapturedQuantity"}),
            "depth": ask_depth,
            "lowestAsk": {"$ref": "#/$defs/LowestAsk"},
            "unconfirmedOffers": _nullable(_obj({
                "count": count, "futureCount": count, "capturedQuantity": {"$ref": "#/$defs/CapturedQuantity"},
                "lowestAsk": {"$ref": "#/$defs/LowestAsk"}, "reasons": {"$ref": "#/$defs/ReasonList"}}))})),
        "PeerScope": _obj({"kind": {"enum": list(ma.PEER_SCOPE_KINDS)}, "scopeId": {"type": "string", "minLength": 1},
                           "scopeLabel": {"enum": [ma.RESEARCH_PANEL_SCOPE_LABEL, ma.MARKET_ROSTER_SCOPE_LABEL]},
                           "cohortRevision": {"type": "string", "minLength": 1},
                           "claimsAllPokemon": {"const": False}}),
        "Peers": _nullable(_obj({
            "label": {"const": ma.PERCENTILE_LABEL}, "tiePolicy": {"const": ma.TIE_POLICY_VERSION},
            "populationKey": {"type": "string"}, "state": {"enum": ["AVAILABLE", "UNAVAILABLE", "NO_PEERS",
                                                                     "INSUFFICIENT_PEERS", "ALL_ZERO", "ALL_TIED"]},
            "reasons": {"$ref": "#/$defs/ReasonList"},
            "eligibleOtherPeerCount": count, "quarantinedPeerCount": count, "duplicatePeerRowCount": count,
            "activityPercentile": _nullable({"$ref": "#/$defs/DecimalString"}),
            "strictBelowPct": _nullable({"$ref": "#/$defs/DecimalString"}),
            "tieCount": {"$ref": "#/$defs/NullableCount"},
            "scope": _nullable({"$ref": "#/$defs/PeerScope"}),
            "scopeLabel": {"type": ["string", "null"]}, "claimsAllPokemon": {"const": False}})),
        "Fingerprint": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        # ---- dated series (fma_activity_series_v1) ----
        "ProofState": {"enum": ["PROVEN", "OBSERVED_ONLY"]},
        "SaleCountPoint": _obj({"date": date_ref, "observedCount": positive, "proofState": {"$ref": "#/$defs/ProofState"},
                                "firstIngestedAt": {"$ref": "#/$defs/NullableDateTime"},
                                "lastIngestedAt": {"$ref": "#/$defs/NullableDateTime"},
                                "ingestedAfterReconciliation": {"type": ["boolean", "null"]}}),
        "SalePricePoint": _obj({"date": date_ref, "recordCount": positive, "low": {"$ref": "#/$defs/Money"},
                                "median": {"$ref": "#/$defs/Money"}, "high": {"$ref": "#/$defs/Money"}}),
        "SupplyListingPoint": _obj({"date": date_ref, "providerConfirmedAt": dt_ref, "firstCollectedAt": dt_ref,
                                    "lastCollectedAt": dt_ref, "collectionCount": positive,
                                    "confirmationsOnDate": positive, "stateAtCollection": {"$ref": "#/$defs/AskState"},
                                    "depth": ask_depth, "value": count}),
        "SupplyQuantityPoint": _obj({"date": date_ref, "providerConfirmedAt": dt_ref,
                                     "provenance": quantity_provenance, "value": count}),
        "AskPricePoint": _obj({"date": date_ref, "providerConfirmedAt": dt_ref,
                               "basis": {"$ref": "#/$defs/LowestAskBasis"}, "price": {"$ref": "#/$defs/Money"}}),
        "GroupSaleCountPoint": _obj({"date": date_ref, "observedCount": positive, "contributingConstituents": positive,
                                     "provenConstituents": count, "proofState": {"$ref": "#/$defs/ProofState"}}),
        "GroupSupplyPoint": _obj({"date": date_ref, "value": count, "contributingConstituents": positive}),
        "InstrumentSeries": _obj({
            **series_envelope,
            "sales": _obj({"source": {"const": ma.SOLD_SOURCE}, "conditionBasis": {"const": ma.SOLD_CONDITION_BASIS},
                           "currency": {"const": "USD"}, "tier": {"type": "string"},
                           "observationState": {"enum": ["OBSERVED", "NOT_COLLECTED"]},
                           "provenSpan": {"$ref": "#/$defs/NullableDateRange"},
                           "reconciledThrough": {"$ref": "#/$defs/NullableDateTime"},
                           "counts": _axis("SALE_COUNT", "SaleCountPoint"),
                           "prices": _axis("USD", "SalePricePoint")}),
            "supply": _nullable(_obj({
                "source": {"const": ma.ASK_SOURCE}, "conditionBasis": {"const": ma.ASK_CONDITION_BASIS},
                "excludedSnapshots": _obj({"byStateAtCollection": {"type": "object",
                                                                   "additionalProperties": positive},
                                           "outsideActivityRange": count}),
                "listings": _axis("LISTING_COUNT", "SupplyListingPoint"),
                "quantity": _axis("LISTED_QUANTITY", "SupplyQuantityPoint"),
                "lowestAsk": _axis("USD", "AskPricePoint")}))}),
        "GroupSeries": _obj({
            **series_envelope, "rosterDenominator": count,
            "sales": _obj({"source": {"const": ma.SOLD_SOURCE}, "conditionBasis": {"const": ma.SOLD_CONDITION_BASIS},
                           "tier": {"const": "RAW"}, "provenSpan": {"$ref": "#/$defs/NullableDateRange"},
                           "counts": _axis("SALE_COUNT", "GroupSaleCountPoint")}),
            "supply": _obj({"source": {"const": ma.ASK_SOURCE}, "conditionBasis": {"const": ma.ASK_CONDITION_BASIS},
                            "aggregation": {"const": ma.GROUP_SUPPLY_AGGREGATION},
                            "listings": _axis("LISTING_COUNT", "GroupSupplyPoint"),
                            "quantity": _axis("LISTED_QUANTITY", "GroupSupplyPoint")})}),
    }
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "common.schema.json",
            "title": "Focused Market Activity V1 shared definitions", "$defs": defs}


def _envelope(kind: str, request_schema: str, body: dict[str, Any]) -> dict[str, Any]:
    props = {"kind": {"const": kind}, "contractVersion": {"const": ma.CONTRACT_VERSION},
             "versions": _ref("Versions"), "policy": _ref("Policy"),
             "request": {"$ref": f"{request_schema}#"}, "evaluatedAt": _ref("DateTime"),
             "activityGenerationId": _nullable(_ref("Uuid")),
             "availability": _ref("Availability"), "evidenceFingerprint": _ref("Fingerprint"), **body}
    return props


def request_schemas() -> dict[str, dict[str, Any]]:
    """Structured POST read bodies. Three independent pins on every read:
    activityGenerationId (activity projection), rosterRef (immutable roster)
    and, for pages, an opaque revision-bound cursor."""
    base = {"marketKey": {"type": "string", "minLength": 1}, "activityGenerationId": _ref("Uuid"),
            "rosterRef": _ref("RosterRevision"), "asOf": _ref("Date"), "windowDays": _ref("WindowDays")}
    return {
        "activity_request.schema.json": _obj({**base, "chartRange": _ref("NullableDateRange")}),
        "constituent_page_request.schema.json": _obj({**base,
                                                       "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                                                       "cursor": _nullable(_ref("Cursor"))}),
        "instrument_detail_request.schema.json": _obj({**base, "instrumentKey": {"type": "string", "minLength": 1},
                                                        "chartRange": _ref("NullableDateRange")}),
    }


def response_schemas() -> dict[str, dict[str, Any]]:
    instrument = _nullable(_obj({"instrumentKey": _ref("InstrumentKey"), "asset": {"const": "cards"},
                                 "cardVariantId": _ref("Uuid"), "canonicalCardId": _nullable(_ref("Uuid")),
                                 "stream": {"enum": ["RAW", "GRADED"]}, "tier": {"type": "string"},
                                 "grading": _ref("Grading")}))
    sales = _nullable(_obj({"source": {"const": ma.SOLD_SOURCE}, "currency": {"const": "USD"},
                            "conditionBasis": {"const": ma.SOLD_CONDITION_BASIS}, "tier": {"type": "string"},
                            "observation": _ref("Observation"),
                            "windows": {"type": "array", "minItems": 4, "maxItems": 4, "items": _ref("SalesWindow")},
                            "excludedRecordCounts": {"type": "object", "additionalProperties": {"type": "integer",
                                                                                                "minimum": 1}}}))
    detail = _envelope("instrumentDetail", "instrument_detail_request.schema.json", {
        "instrument": instrument, "roster": _ref("Roster"), "sales": sales, "asks": _ref("Asks"),
        "peers": _ref("Peers"), "series": _nullable(_ref("InstrumentSeries")), "capabilities": _ref("Capabilities")})
    row_caps = {k: _ref("ExpiringCapability" if k in ma.EXPIRING_FEATURES else "Capability")
                for k in ("saleCount", "observedSales", "salePriceSummary", "currentAsks")}
    row = _obj({"rank": {"type": "integer", "minimum": 1}, "instrumentKey": {"type": "string"},
                "cardVariantId": _nullable(_ref("Uuid")), "availability": _ref("Availability"),
                "observationState": {"enum": ["OBSERVED", "NOT_COLLECTED"]},
                "windowReadiness": {"enum": list(ma.READINESS_ORDER)},
                "observedCount": _ref("NullableCount"), "provenCount": _ref("NullableCount"),
                "medianPrice": _ref("NullableMoney"), "askState": _nullable(_ref("AskState")),
                "lowestAsk": _ref("LowestAsk"), "capabilities": _obj(row_caps)})
    page = _envelope("constituentActivityPage", "constituent_page_request.schema.json", {
        "roster": _ref("Roster"),
        "page": _nullable(_obj({"afterRank": {"type": "integer", "minimum": 0},
                                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                                "totalCount": {"type": "integer", "minimum": 0},
                                "nextCursor": _nullable(_ref("Cursor"))})),
        "rows": {"type": "array", "maxItems": 100, "items": row}})
    group = _envelope("groupActivity", "activity_request.schema.json", {
        "label": {"const": ma.MEMBERSHIP_LABEL}, "roster": _ref("Roster"),
        "coverage": _nullable(_obj({k: {"type": "integer", "minimum": 0} for k in (
            "rosterDenominator", "windowProven", "windowPartial", "windowUnproven", "notCollected",
            "unavailable")})),
        "totals": _nullable(_obj({"windowDays": _ref("WindowDays"),
                                  "provenSaleCount": _ref("NullableCount"),
                                  "provenConstituentCount": {"type": "integer", "minimum": 0},
                                  "observedSaleCountLowerBound": _ref("NullableCount"),
                                  "observedConstituentCount": {"type": "integer", "minimum": 0}})),
        "series": _nullable(_ref("GroupSeries"))})
    manifest = _obj({
        "manifestVersion": {"const": FIXTURE_SET_VERSION}, "contractVersion": {"const": ma.CONTRACT_VERSION},
        "versions": _ref("Versions"), "policy": _ref("Policy"),
        "schemas": {"type": "object", "additionalProperties": _ref("Fingerprint")},
        "fixtures": {"type": "array", "minItems": 1, "items": _obj({
            "fixtureId": {"type": "string"}, "scenario": {"type": "string"}, "file": {"type": "string"},
            "assembler": {"enum": ["instrument_detail", "constituent_page", "group_activity"]},
            "requestSchema": {"type": "string"}, "responseSchema": {"type": "string"},
            "sha256": _ref("Fingerprint"), "expectedAvailability": {"enum": ["AVAILABLE", "PARTIAL",
                                                                             "UNAVAILABLE"]}})},
    })
    out = {"instrument_detail_response.schema.json": _obj(detail),
           "constituent_page_response.schema.json": _obj(page),
           "activity_response.schema.json": _obj(group),
           "fixture_manifest.schema.json": manifest}
    return out


def all_schemas() -> dict[str, dict[str, Any]]:
    schemas = {"common.schema.json": common_schema()}
    for name, body in {**request_schemas(), **response_schemas()}.items():
        schemas[name] = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": name,
                         "title": name.replace(".schema.json", ""), **body}
    return schemas


# ---------------------------------------------------------------------------
# Fixture inputs (synthetic; never production data)
# ---------------------------------------------------------------------------
GEN = "5f0c7a52-3b1e-4b8e-9a51-2d7c1f0e9a10"
OTHER_GEN = "9b2d4e61-7c3a-4f18-8e27-6a1b0c9d8e7f"
ACTIVITY_GEN = "7c1d2e3f-4a5b-4c6d-8e7f-0a1b2c3d4e5f"
ACTIVITY_GEN_NEXT = "8d2e3f4a-5b6c-4d7e-9f80-1b2c3d4e5f60"
MARKET = "set:fixture-modern-set"
V_A = "00000000-0000-4000-8000-0000000000a1"
V_A_REV = "00000000-0000-4000-8000-0000000000a2"
V_B = "00000000-0000-4000-8000-0000000000b1"
V_C = "00000000-0000-4000-8000-0000000000c1"
CANON_A = "10000000-0000-4000-8000-0000000000a0"
PROVIDER_A, PROVIDER_B, PROVIDER_C = "900001", "900002", "900003"
AS_OF = "2026-09-29"
EVALUATED_AT = "2026-09-30T12:00:00Z"
RECONCILED = "2026-09-30T06:00:00Z"
COLLECTION_RUN = "run-fixture-20260930"
CORE_PANEL_COHORT = "core_panel_v1:9e3068ffb2e644e3dab2f5c237271afa4efe061ed8f3139187dc9e8331bd1d1f"
ROSTER_REF = {"kind": "SURFACE_V2_GENERATION", "generationId": GEN, "marketKey": MARKET}
ACTIVITY_GENERATION = {"activityGenerationId": ACTIVITY_GEN, "state": "SERVING", "rosterRef": ROSTER_REF}
ROSTER = {"asOf": AS_OF, "denominator": 3, "memberVariantIds": [V_A, V_B, V_C]}
CANDIDATES_A = [{"id": V_A, "edition": None, "printingType": "holo", "specialType": None},
                {"id": V_A_REV, "edition": None, "printingType": "reverse-holo", "specialType": None}]
CHART_RANGE_365 = {"startDate": "2025-09-30", "endDate": AS_OF}


def _raw_key(variant: str) -> str:
    return f"card:{variant}:raw"


def _record(n: int, sold: str, price: str, **extra: Any) -> dict[str, Any]:
    ingested = (date.fromisoformat(sold) + timedelta(days=1)).isoformat() + "T01:00:00Z"
    row = {"source": ma.SOLD_SOURCE, "providerCardId": PROVIDER_A, "listingId": str(700000 + n), "price": price,
           "currency": "USD", "soldAt": sold, "ingestedAt": ingested, "collectedAt": "2026-09-30T05:00:00Z",
           "attribution": "exact", "providerVariant": "Holofoil", "grader": None, "grade": None,
           "gradeQualifier": None, "graded": False}
    row.update(extra)
    return row


def _raw_records() -> list[dict[str, Any]]:
    sold_dates = ["2026-09-28", "2026-09-27", "2026-09-25", "2026-09-24", "2026-09-20", "2026-09-15",
                  "2026-09-10", "2026-09-02", "2026-08-20", "2026-08-01", "2026-07-15", "2026-05-01"]
    prices = ["41.00", "39.50", "42.25", "40.00", "38.75", "43.10", "40.50", "37.99", "36.00", "35.50",
              "33.00", "30.00"]
    rows = [_record(i, d, p) for i, (d, p) in enumerate(zip(sold_dates, prices))]
    rows.append(_record(12, "2026-09-26", "44.00", attribution="shared"))            # excluded: shared
    rows.append(_record(13, "2026-09-26", "120.00", grader="PSA", grade="10", graded=True))  # other tier
    rows.append(dict(rows[0]))                                                         # exact duplicate
    rows.append(_record(14, "2026-09-22", "45.00", providerVariant=None, attribution="unknown"))
    rows.append(_record(15, "2026-09-23", "not-a-price"))                              # invalid row
    return rows


def _page(index: int, hi: str | None, lo: str | None, rows: int, has_more: bool) -> dict[str, Any]:
    return {"pageIndex": index, "inputCursorHash": None if index == 0 else f"c{index - 1:03d}",
            "outputCursorHash": f"c{index:03d}" if has_more else None, "hasMore": has_more,
            "maxSoldAt": hi, "minSoldAt": lo, "rowCount": rows, "filterFingerprint": "f-combined",
            "fetchedAt": "2026-09-30T05:00:00Z"}


def _walk(pages: list[dict[str, Any]], *, reconciled: str | None = RECONCILED,
          provider_card: str = PROVIDER_A, tag: str = "full") -> dict[str, Any]:
    walk_id = f"walk-{provider_card}-{tag}"
    right = None if reconciled is None else {
        "completed": True, "reconciledThrough": reconciled, "providerCardId": provider_card, "stream": "COMBINED",
        "filterFingerprint": "f-combined", "graderFilter": None, "gradeFilter": None, "headWalkId": walk_id,
        "collectionRunId": COLLECTION_RUN, "committed": True}
    return {"walkId": walk_id, "providerCardId": provider_card, "collectionRunId": COLLECTION_RUN, "committed": True,
            "stream": "COMBINED", "combinedSemanticsVerified": True, "graderFilter": None, "gradeFilter": None,
            "sort": "date_desc", "startedFromHead": True, "filterFingerprint": "f-combined", "pages": pages,
            "rightEdge": right}


FULL_WALK = _walk([_page(0, "2026-09-29", "2026-08-20", 20, True), _page(1, "2026-08-20", "2026-03-01", 20, True)])


def _offer(price: str, ship: str | None, qty: int, confirmed: str | None, updated: str | None = None,
           ship_prov: str = "EXPLICIT", qty_prov: str = "EXPLICIT") -> dict[str, Any]:
    return {"itemPrice": price, "shippingPrice": ship, "shippingProvenance": ship_prov, "quantity": qty,
            "quantityProvenance": qty_prov, "providerSnapshotAt": confirmed, "listingUpdatedAt": updated}


def _fresh_asks(**over: Any) -> dict[str, Any]:
    offers = [_offer("44.00", "0.00", 2, "2026-09-30T08:00:00Z", "2026-09-20T00:00:00Z"),
              _offer("42.00", "4.99", 1, "2026-09-30T08:00:00Z", "2026-09-29T00:00:00Z"),
              _offer("45.50", "1.00", 1, "2026-09-30T08:00:00Z")]
    snap = {"observationState": "OBSERVED", "observedAt": "2026-09-30T09:00:00Z", "hasMore": True,
            "requestedDepth": 19, "sourceConfirmedAt": None, "offers": offers}
    snap.update(over)
    return snap


def _peer_scope() -> dict[str, Any]:
    return {"kind": "RESEARCH_PANEL", "panelId": ma.RESEARCH_PANEL_ID, "cohortRevision": CORE_PANEL_COHORT}


def _peers(count: int, values: list[int] | None = None, window: int = 30) -> dict[str, Any]:
    scope = ma.peer_scope(_peer_scope())
    start, end = ma.closed_window(AS_OF, window)
    key = ma.peer_population_key(window_start=start, window_end=end, source=ma.SOLD_SOURCE, currency="USD",
                                 tier="RAW", coverage="PROVEN", scope_key=ma.peer_scope_key(scope))
    vals = values if values is not None else [(i * 7) % 15 for i in range(count)]
    rows = [{"instrumentKey": f"card:00000000-0000-4000-8000-{i:012d}:raw", "populationKey": key, "value": v}
            for i, v in enumerate(vals)]
    rows.append({"instrumentKey": _raw_key(V_A), "populationKey": key, "value": 9})  # target: excluded
    rows.append({"instrumentKey": "card:00000000-0000-4000-8000-999999999999:raw",
                 "populationKey": key.replace("|PROVEN|", "|UNPROVEN|"), "value": 3})  # other coverage
    if rows[:-2]:
        rows.append(dict(rows[0]))                                                     # duplicate row: once
    stale = ma.peer_population_key(window_start="2026-06-01", window_end="2026-06-30", source=ma.SOLD_SOURCE,
                                   currency="USD", tier="RAW", coverage="PROVEN", scope_key=ma.peer_scope_key(scope))
    rows.append({"instrumentKey": "card:00000000-0000-4000-8000-888888888888:raw", "populationKey": stale,
                 "value": 4})                                                          # same duration, other dates
    return {"scope": _peer_scope(), "values": rows}


def _sold(records: list[dict[str, Any]] | None = None, walks: list[dict[str, Any]] | None = None,
          **over: Any) -> dict[str, Any]:
    sold = {"providerCardId": PROVIDER_A, "collectionRecord": None, "candidateScope": "FULL_CARD_VARIANT_SET",
            "candidates": CANDIDATES_A, "records": _raw_records() if records is None else records,
            "walks": [FULL_WALK] if walks is None else walks}
    sold.update(over)
    return sold


def _detail(request_over: dict[str, Any] | None = None, **over: Any) -> dict[str, Any]:
    request = {"marketKey": MARKET, "activityGenerationId": ACTIVITY_GEN, "rosterRef": ROSTER_REF,
               "instrumentKey": _raw_key(V_A), "asOf": AS_OF, "windowDays": 30, "chartRange": None}
    request.update(request_over or {})
    inputs = {"request": request, "asset": "cards", "servedGenerationId": GEN,
              "activityGeneration": ACTIVITY_GENERATION, "evaluatedAt": EVALUATED_AT,
              "canonicalCardId": CANON_A, "roster": ROSTER, "sold": _sold(),
              "asks": _fresh_asks(), "askHistory": [], "previousAskConfirmation": None, "peers": _peers(35)}
    inputs.update(over)
    return inputs


def _graded_records() -> list[dict[str, Any]]:
    good = [_record(100 + i, d, p, grader="PSA", grade="10", graded=True) for i, (d, p) in enumerate([
        ("2026-09-28", "160.00"), ("2026-09-25", "155.00"), ("2026-09-21", "158.50"),
        ("2026-09-14", "150.00"), ("2026-09-08", "149.99"), ("2026-09-03", "162.00")])]
    bad = [
        _record(120, "2026-09-26", "140.00", grader="PSA", grade=None, graded=True),    # missing grade
        _record(121, "2026-09-26", "141.00", grader=None, grade="10", graded=True),     # missing grader
        _record(122, "2026-09-26", "142.00", graded=True),                             # graded flag only
        _record(123, "2026-09-26", "210.00", grader="PSA", grade="10", gradeQualifier="Gem+", graded=True),
        _record(124, "2026-09-26", "95.00", grader="CGC", grade="9.5", graded=True),   # other tier
        _record(125, "2026-09-26", "38.00"),                                            # raw: other tier
    ]
    return good + bad


def _ask_history() -> list[dict[str, Any]]:
    """Multi-date supply history: repeated confirmation, gaps, an unconfirmed
    snapshot, an explicit proven-zero date and one confirmation outside the
    activity range."""
    def snap(observed: str, offers: list[dict[str, Any]], has_more: bool, source_confirmed: str | None = None):
        return {"observationState": "OBSERVED", "observedAt": observed, "hasMore": has_more, "requestedDepth": 19,
                "sourceConfirmedAt": source_confirmed, "offers": offers}
    day20 = [_offer("40.00", "0.00", 1, "2026-09-20T08:00:00Z"), _offer("41.50", "1.50", 2, "2026-09-20T08:00:00Z"),
             _offer("43.00", "0.00", 1, "2026-09-20T08:00:00Z")]
    day25 = [_offer("39.00", None, 1, "2026-09-25T07:00:00Z", ship_prov="UNKNOWN"),
             _offer("42.00", "0.00", 1, "2026-09-25T07:00:00Z", qty_prov="DEFAULTED")]
    return [
        snap("2026-03-01T10:00:00Z", [_offer("30.00", "0.00", 1, "2026-03-01T09:00:00Z")], False),  # outside range
        snap("2026-09-20T09:00:00Z", day20, True),
        snap("2026-09-21T09:00:00Z", day20, True),                               # repeated source confirmation
        snap("2026-09-25T08:00:00Z", day25, False),
        snap("2026-09-27T08:00:00Z", [_offer("38.00", "0.00", 1, None)], False),   # unconfirmed: excluded
        snap("2026-09-28T07:00:00Z", [], False, "2026-09-28T06:00:00Z"),           # explicit proven zero
    ]


def _series_records() -> list[dict[str, Any]]:
    rows = _raw_records()
    # Late ingestion: sold inside the 30d window, ingested after the right-edge
    # reconciliation (2026-09-30T06:00Z) -> 30/90/180d windows are not proven.
    rows.append(_record(16, "2026-09-05", "39.25", ingestedAt="2026-09-30T09:00:00Z"))
    rows.append(_record(17, "2026-09-28", "40.25"))                                 # two sales on one date
    rows.append(_record(18, "2026-02-15", "28.00"))                                 # before the activity range
    return rows


def scenarios() -> list[dict[str, Any]]:
    partial_walk = _walk([_page(0, "2026-09-29", "2026-08-10", 20, True), _page(1, "2026-08-10", "2026-07-02", 20, True)])
    zero_walk = _walk([_page(0, "2026-02-10", "2026-01-05", 3, False)], tag="zero")
    zero_records = [_record(200, "2026-02-10", "12.00"), _record(201, "2026-01-20", "11.50"),
                    _record(202, "2026-01-05", "11.00")]
    legacy_offers = [_offer("41.00", "0.00", 1, "2026-09-24T02:06:10Z", "2026-09-24T02:06:10Z"),
                     _offer("43.00", "0.00", 1, "2026-09-23T20:12:49Z", "2026-07-22T23:27:16Z")]
    for offer in legacy_offers:          # legacy rows carry no provenance markers
        offer.pop("shippingProvenance")
        offer.pop("quantityProvenance")
    future_walk = _walk(FULL_WALK["pages"], reconciled="2027-01-01T00:00:00Z", tag="future")
    mixed_asks = _fresh_asks(hasMore=False, offers=_fresh_asks()["offers"] + [_offer("1.00", "0.00", 5, None)])
    page_cursor = ma.encode_cursor(ma._cursor_payload(_roster_inputs({"limit": 2})["request"], 30, 2))
    return [
        {"fixtureId": "fma_fixture_01", "scenario": "fresh_complete", "assembler": "instrument_detail",
         "description": "Proven 7/30/90/180d raw windows without lifetime exhaustion, fresh landed asks, 35 "
                        "unique peers (a duplicate peer row counts once; a same-duration other-date peer "
                        "population is excluded).",
         "inputs": _detail()},
        {"fixtureId": "fma_fixture_02", "scenario": "partial_sales", "assembler": "instrument_detail",
         "description": "Walk stopped inside the 90d boundary date: 7/30 proven, 90 partial, 180 unproven.",
         "inputs": _detail({"windowDays": 90}, sold=_sold(walks=[partial_walk]), peers=None)},
        {"fixtureId": "fma_fixture_03", "scenario": "stale_asks", "assembler": "instrument_detail",
         "description": "Asks collected today but provider-confirmed days earlier; legacy shipping/quantity.",
         "inputs": _detail(asks={"observationState": "OBSERVED", "observedAt": "2026-09-29T22:08:05Z",
                                 "hasMore": True, "requestedDepth": 19, "sourceConfirmedAt": None,
                                 "offers": legacy_offers},
                           previousAskConfirmation="2026-09-23T20:12:49Z")},
        {"fixtureId": "fma_fixture_04", "scenario": "zero_with_proof", "assembler": "instrument_detail",
         "description": "Exhausted walk + reconciled right edge prove zero sales; empty asks with source freshness.",
         "inputs": _detail(sold=_sold(records=zero_records, walks=[zero_walk]),
                           asks={"observationState": "OBSERVED", "observedAt": "2026-09-30T09:00:00Z",
                                 "hasMore": False, "requestedDepth": 19,
                                 "sourceConfirmedAt": "2026-09-30T07:30:00Z", "offers": []},
                           peers=_peers(35, [0] * 35))},
        {"fixtureId": "fma_fixture_05", "scenario": "not_collected", "assembler": "instrument_detail",
         "description": "No sold evidence, no receipt, no collection record, no supply snapshot: every count is "
                        "null, never zero.",
         "inputs": _detail(sold=_sold(records=[], walks=[]), asks=None, peers=None)},
        {"fixtureId": "fma_fixture_06", "scenario": "missing_grade", "assembler": "instrument_detail",
         "description": "PSA 10 tier: incomplete/unknown-qualifier slabs are excluded, never raw, never PSA 10.",
         "inputs": _detail({"instrumentKey": f"card:{V_A}:graded:PSA:10:-"},
                           sold=_sold(records=_graded_records()), asks=None, peers=None)},
        {"fixtureId": "fma_fixture_07", "scenario": "insufficient_peers", "assembler": "instrument_detail",
         "description": "Only 12 other unique eligible peers (< 30): no Activity percentile badge.",
         "inputs": _detail(peers=_peers(12))},
        {"fixtureId": "fma_fixture_08", "scenario": "unsupported_asset", "assembler": "instrument_detail",
         "description": "Sealed markets are not supported by activity V1.",
         "inputs": _detail(asset="sealed")},
        {"fixtureId": "fma_fixture_09", "scenario": "generation_mismatch", "assembler": "instrument_detail",
         "description": "The served surface generation differs from the pinned roster generation: nothing mixes.",
         "inputs": _detail(servedGenerationId=OTHER_GEN)},
        {"fixtureId": "fma_fixture_10", "scenario": "constituent_page", "assembler": "constituent_page",
         "description": "Rank-ordered first page over the full 3-member roster, limit 2, opaque next cursor.",
         "inputs": _roster_inputs({"limit": 2, "cursor": None})},
        {"fixtureId": "fma_fixture_11", "scenario": "group_activity", "assembler": "group_activity",
         "description": "Activity for current constituents with full-roster coverage and a group series under a "
                        "365-day canonical chart range.",
         "inputs": _roster_inputs({"chartRange": CHART_RANGE_365})},
        {"fixtureId": "fma_fixture_12", "scenario": "legacy_no_receipts", "assembler": "instrument_detail",
         "description": "FMA-0.1 F1: persisted legacy sales, no walk receipt: exact observed counts and dated "
                        "observations stand; proven counts, saleCount and peer ranks stay unavailable.",
         "inputs": _detail(sold=_sold(walks=[]))},
        {"fixtureId": "fma_fixture_13", "scenario": "future_right_edge", "assembler": "instrument_detail",
         "description": "FMA-0.1 F2: a completed right edge dated 2027 at a 2026 evaluation is never proof.",
         "inputs": _detail(sold=_sold(walks=[future_walk]), peers=None)},
        {"fixtureId": "fma_fixture_14", "scenario": "mixed_unconfirmed_asks", "assembler": "instrument_detail",
         "description": "FMA-0.1 F3: fresh confirmed offers plus an unconfirmed $1 offer: PARTIALLY_CONFIRMED, "
                        "the $1 offer never sets the ask or depth, currentAsks withheld.",
         "inputs": _detail(asks=mixed_asks, peers=None)},
        {"fixtureId": "fma_fixture_15", "scenario": "multi_date_series", "assembler": "instrument_detail",
         "description": "FMA-0.1 F4: sparse daily series with missing dates, late ingestion, repeated source "
                        "confirmations, a proven-zero supply date and a 365-day canonical range longer than "
                        "the 180-day activity range.",
         "inputs": _detail({"chartRange": CHART_RANGE_365}, sold=_sold(records=_series_records()),
                           askHistory=_ask_history(), peers=None)},
        {"fixtureId": "fma_fixture_16", "scenario": "constituent_page_cursor", "assembler": "constituent_page",
         "description": "FMA-0.1 F5: second page read through the opaque cursor from fixture 10.",
         "inputs": _roster_inputs({"limit": 2, "cursor": page_cursor})},
        {"fixtureId": "fma_fixture_17", "scenario": "cursor_mismatch", "assembler": "constituent_page",
         "description": "FMA-0.1 F5: activity refreshed under the SAME market generation; a cursor from the old "
                        "activity generation is rejected instead of mixing pages.",
         "inputs": _roster_inputs({"limit": 2, "cursor": page_cursor, "activityGenerationId": ACTIVITY_GEN_NEXT},
                                  activity_generation={**ACTIVITY_GENERATION,
                                                       "activityGenerationId": ACTIVITY_GEN_NEXT})},
        {"fixtureId": "fma_fixture_18", "scenario": "activity_generation_expired", "assembler": "constituent_page",
         "description": "FMA-0.1 F5: the pinned activity generation was retired: restart from the first page.",
         "inputs": _roster_inputs({"limit": 2, "cursor": page_cursor},
                                  activity_generation={**ACTIVITY_GENERATION, "state": "RETIRED"})},
        {"fixtureId": "fma_fixture_19", "scenario": "group_roster_101", "assembler": "group_activity",
         "description": "FMA-0.1 F6: a 101-member roster (larger than one 100-row page) aggregated in full, "
                        "members supplied in shuffled order.",
         "inputs": _large_roster_inputs(101)},
    ]


def _roster_inputs(request_over: dict[str, Any], *,
                   activity_generation: dict[str, Any] | None = None) -> dict[str, Any]:
    partial_walk = _walk([_page(0, "2026-09-29", "2026-09-10", 20, True)], provider_card=PROVIDER_B, tag="head")
    members = [
        {"rank": 1, "cardVariantId": V_A, "instrumentKey": _raw_key(V_A),
         "detailInputs": {"canonicalCardId": CANON_A, "sold": _sold(),
                          "asks": _fresh_asks(), "askHistory": _ask_history()[1:4], "peers": None}},
        {"rank": 2, "cardVariantId": V_B, "instrumentKey": _raw_key(V_B),
         "detailInputs": {"canonicalCardId": None,
                          "sold": {"providerCardId": PROVIDER_B, "collectionRecord": None,
                                   "candidateScope": "FULL_CARD_VARIANT_SET",
                                   "candidates": [{"id": V_B, "edition": None, "printingType": "holo"}],
                                   "records": [_record(300, "2026-09-20", "5.00", providerCardId=PROVIDER_B),
                                               _record(301, "2026-09-12", "5.25", providerCardId=PROVIDER_B)],
                                   "walks": [partial_walk]},
                          "asks": None, "peers": None}},
        {"rank": 3, "cardVariantId": V_C, "instrumentKey": _raw_key(V_C),
         "detailInputs": {"canonicalCardId": None,
                          "sold": {"providerCardId": PROVIDER_C, "collectionRecord": None,
                                   "candidateScope": "FULL_CARD_VARIANT_SET", "candidates": [], "records": [],
                                   "walks": []}, "asks": None, "peers": None}},
    ]
    request = {"marketKey": MARKET, "activityGenerationId": ACTIVITY_GEN, "rosterRef": ROSTER_REF, "asOf": AS_OF,
               "windowDays": 30, **request_over}
    return {"request": request, "asset": "cards", "servedGenerationId": GEN,
            "activityGeneration": activity_generation or ACTIVITY_GENERATION, "evaluatedAt": EVALUATED_AT,
            "roster": {k: v for k, v in ROSTER.items() if k != "memberVariantIds"}, "members": members}


def _large_roster_inputs(count: int) -> dict[str, Any]:
    members = []
    for rank in range(1, count + 1):
        variant = f"00000000-0000-4000-8000-{rank:012d}"
        provider = f"8{rank:05d}"
        records = []
        if rank % 25 == 1:   # a few constituents have legacy stored rows (observed, never proven)
            records = [_record(1000 + rank, "2026-09-21", "3.00", providerCardId=provider,
                               listingId=f"L{rank}-1"),
                       _record(1000 + rank, "2026-09-18", "3.10", providerCardId=provider,
                               listingId=f"L{rank}-2")]
        members.append({"rank": rank, "cardVariantId": variant, "instrumentKey": _raw_key(variant),
                        "detailInputs": {"canonicalCardId": None,
                                         "sold": {"providerCardId": provider, "collectionRecord": None,
                                                  "candidateScope": "FULL_CARD_VARIANT_SET",
                                                  "candidates": [{"id": variant, "edition": None,
                                                                  "printingType": "holo"}],
                                                  "records": records, "walks": []},
                                         "asks": None, "peers": None}})
    order = sorted(range(count), key=lambda i: (i * 37) % count)   # deterministic shuffle
    request = {"marketKey": MARKET, "activityGenerationId": ACTIVITY_GEN, "rosterRef": ROSTER_REF, "asOf": AS_OF,
               "windowDays": 30, "chartRange": None}
    return {"request": request, "asset": "cards", "servedGenerationId": GEN,
            "activityGeneration": ACTIVITY_GENERATION, "evaluatedAt": EVALUATED_AT,
            "roster": {"asOf": AS_OF, "denominator": count}, "members": [members[i] for i in order]}


ASSEMBLERS = {
    "instrument_detail": (ma.assemble_instrument_detail, "instrument_detail_request.schema.json",
                          "instrument_detail_response.schema.json"),
    "constituent_page": (ma.assemble_constituent_page, "constituent_page_request.schema.json",
                         "constituent_page_response.schema.json"),
    "group_activity": (ma.aggregate_group_activity, "activity_request.schema.json",
                       "activity_response.schema.json"),
}


def build_fixture(spec: dict[str, Any]) -> dict[str, Any]:
    assembler, request_schema, response_schema = ASSEMBLERS[spec["assembler"]]
    expected = assembler(spec["inputs"])
    return {**spec, "requestSchema": request_schema, "responseSchema": response_schema, "expected": expected}


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def render() -> dict[Path, str]:
    files: dict[Path, str] = {}
    schemas = all_schemas()
    for name, body in schemas.items():
        files[CONTRACTS / name] = _dump(body)
    entries = []
    for spec in scenarios():
        fixture = build_fixture(spec)
        name = f"{spec['fixtureId']}_{spec['scenario']}.json"
        text = _dump(fixture)
        files[FIXTURES / name] = text
        entries.append({"fixtureId": spec["fixtureId"], "scenario": spec["scenario"], "file": name,
                        "assembler": spec["assembler"], "requestSchema": fixture["requestSchema"],
                        "responseSchema": fixture["responseSchema"], "sha256": ma.fingerprint(json.loads(text)),
                        "expectedAvailability": fixture["expected"]["availability"]["state"]})
    manifest = {"manifestVersion": FIXTURE_SET_VERSION, "contractVersion": ma.CONTRACT_VERSION,
                "versions": ma._versions(), "policy": ma.DEFAULT_POLICY.as_contract(),
                "schemas": {name: ma.fingerprint(body) for name, body in sorted(schemas.items())},
                "fixtures": entries}
    files[FIXTURES / "manifest.json"] = _dump(manifest)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = render()
    if args.write:
        for path, text in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
        registry = SchemaRegistry(CONTRACTS)
        for path in sorted(FIXTURES.glob("fma_fixture_*.json")):
            fixture = json.loads(path.read_text(encoding="utf-8"))
            errors = registry.validate(fixture["inputs"]["request"], fixture["requestSchema"])
            errors += registry.validate(fixture["expected"], fixture["responseSchema"])
            if errors:
                raise SystemExit(f"{path.name}: {errors[:5]}")
        print(f"wrote {len(files)} files; manifest fingerprint "
              f"{content_fingerprint(FIXTURES / 'manifest.json')}")
        return 0
    drift = [str(p.relative_to(ROOT)) for p, text in files.items()
             if not p.exists() or json.loads(p.read_text(encoding="utf-8")) != json.loads(text)]
    print(json.dumps({"drift": drift}, indent=2))
    return 1 if drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
