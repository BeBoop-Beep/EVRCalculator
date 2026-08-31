from ...clients.tcgplayer_client import TCGPlayerClient
from ...parsers.tcgplayer_parser import TCGPlayerParser
from ..dto_builders.tcgplayer_dto_builder import TCGPlayerDTOBuilder
from backend.db.controllers.ingest_controller import IngestController
from backend.db.repositories.card_variant_repository import ExternalVariantIdentityConflict
from backend.db.services.scrape_failure_classification import (
    ERROR_EXTERNAL_VARIANT_IDENTITY_CONFLICT,
)
from collections import OrderedDict
import copy
import json
import sys
import os
import re

# Add path to import from db folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))


class TCGPlayerResponseProvenanceError(RuntimeError):
    """The provider response contradicts the configured source identity."""


def _normalized_evidence(values):
    return sorted({str(value).strip() for value in values if value is not None and str(value).strip()})


def _normalized_numeric_evidence(values):
    """Return raw and integer-equivalent numeric evidence for diagnostics."""
    raw = _normalized_evidence(values)
    return raw, sorted({str(int(value, 10)) for value in raw}, key=int)


def _group_id_from_url(url):
    match = re.search(r"/priceguide/set/([^/?#]+)/", str(url or ""), flags=re.I)
    return match.group(1) if match else None


def validate_card_response_provenance(config, raw_data, transport_provenance=None):
    """Fail closed when present TCGplayer source evidence contradicts config."""
    requested_url = str(getattr(config, "CARD_DETAILS_URL", "") or "")
    requested_group_id = _group_id_from_url(requested_url)
    expected_group_id = str(getattr(config, "TCGPLAYER_SET_ID", "") or "").strip() or None
    expected_set = str(getattr(config, "TCGPLAYER_SET_NAME", "") or "").strip() or None
    expected_abbreviation = str(
        getattr(config, "TCGPLAYER_SET_ABBREVIATION", "") or ""
    ).strip() or None
    expected_denominators = getattr(
        config, "TCGPLAYER_EXPECTED_CARD_DENOMINATORS", None)
    if isinstance(expected_denominators, (str, int)):
        expected_denominators = {expected_denominators}
    expected_denominators = expected_denominators or set()
    _expected_raw, expected_denominators = _normalized_numeric_evidence(
        expected_denominators)
    rows = list((raw_data or {}).get("result") or [])

    set_ids = _normalized_evidence(row.get("setID") for row in rows)
    set_labels = _normalized_evidence(row.get("set") for row in rows)
    abbreviations = _normalized_evidence(row.get("setAbbrv") for row in rows)
    raw_denominators, denominators = _normalized_numeric_evidence(
        match.group(1)
        for row in rows
        for match in [re.search(r"/\s*([0-9]+)\s*$", str(row.get("number") or ""))]
        if match
    )
    samples = [
        {"productID": row.get("productID"), "productName": row.get("productName"),
         "number": row.get("number")}
        for row in rows[:10]
    ]
    transport = dict(transport_provenance or {})
    final_url = transport.get("final_url")
    final_group_id = _group_id_from_url(final_url)
    report = {
        **transport,
        "requested_url": requested_url,
        "requested_group_id": requested_group_id,
        "configured_group_id": expected_group_id,
        "response_set_ids": set_ids,
        "response_set_labels": set_labels,
        "response_abbreviations": abbreviations,
        "response_card_denominators_raw": raw_denominators,
        "response_card_denominators": denominators,
        "expected_card_denominators": expected_denominators,
        "representative_products": samples,
    }
    contradictions = []
    if expected_group_id and requested_group_id and expected_group_id != requested_group_id:
        contradictions.append(f"configured group {expected_group_id} != requested group {requested_group_id}")
    if final_group_id and requested_group_id and final_group_id != requested_group_id:
        contradictions.append(f"final response group {final_group_id} != requested group {requested_group_id}")
    if len(set_ids) > 1:
        contradictions.append(f"mixed response set IDs: {set_ids}")
    if requested_group_id and any(value != requested_group_id for value in set_ids):
        contradictions.append(f"response set IDs {set_ids} != requested group {requested_group_id}")
    if len(set_labels) > 1:
        contradictions.append(f"mixed response set labels: {set_labels}")
    if expected_set and any(value.casefold() != expected_set.casefold() for value in set_labels):
        contradictions.append(f"response set labels {set_labels} != expected {expected_set}")
    if len(abbreviations) > 1:
        contradictions.append(f"mixed response abbreviations: {abbreviations}")
    if expected_abbreviation and any(
        value.casefold() != expected_abbreviation.casefold() for value in abbreviations
    ):
        contradictions.append(
            f"response abbreviations {abbreviations} != expected {expected_abbreviation}"
        )
    # A denominator is weak catalog evidence, not a universal set identity.
    # Only configs declaring an explicit provider contract may enforce it.
    if expected_denominators and any(
        value not in expected_denominators for value in denominators
    ):
        contradictions.append(
            f"card denominators {denominators} != expected {expected_denominators}"
        )
    if contradictions:
        report["contradictions"] = contradictions
        raise TCGPlayerResponseProvenanceError(
            "tcgplayer_response_provenance_conflict: "
            + "; ".join(contradictions)
            + " diagnostics="
            + json.dumps(report, sort_keys=True, default=str)
        )
    report["contradictions"] = []
    return report


class TCGScraper:
    def __init__(self, enable_db_ingestion=False, target_market_date=None):
        self.client = TCGPlayerClient()
        self.dto_builder = TCGPlayerDTOBuilder()
        self.enable_db_ingestion = enable_db_ingestion
        self.target_market_date = target_market_date
        self.max_parsed_cache_entries = int(os.getenv("PARSED_CACHE_MAX_ENTRIES", "2"))
        self._parsed_cards_cache = OrderedDict()
        self._parsed_sealed_cache = OrderedDict()
        if enable_db_ingestion:
            self.ingest_controller = IngestController()

    def _cache_parsed(self, cache, key, value):
        cache[key] = copy.deepcopy(value)
        cache.move_to_end(key)
        while len(cache) > self.max_parsed_cache_entries:
            cache.popitem(last=False)
    
    def scrape(self, config, excel_path):
        """Main scraping workflow"""
        
        # Step 1: Fetch raw data
        raw_data = self.client.fetch_price_data(config.CARD_DETAILS_URL)
        provenance_report = validate_card_response_provenance(
            config, raw_data, getattr(self.client, "last_response_provenance", {})
        )
        _raw_count = len(raw_data.get("result", []))
        print(
            f"[DIAG][{config.SET_NAME}] step=fetch "
            f"raw_cards={_raw_count} "
            f"url={config.CARD_DETAILS_URL}"
        )

        # Step 2: Parse data
        parser = TCGPlayerParser(config.PULL_RATE_MAPPING, set_name=config.SET_NAME)
        card_cache_key = (config.CARD_DETAILS_URL, config.SET_NAME)
        if card_cache_key in self._parsed_cards_cache:
            self._parsed_cards_cache.move_to_end(card_cache_key)
            card_dicts = copy.deepcopy(self._parsed_cards_cache[card_cache_key])
        else:
            card_dicts = parser.parse_cards(raw_data)
            self._cache_parsed(self._parsed_cards_cache, card_cache_key, card_dicts)

        print(
            f"[DIAG][{config.SET_NAME}] step=parse "
            f"parsed_cards={len(card_dicts)}"
        )

        sealed_cache_key = (config.SEALED_DETAILS_URL, config.SET_NAME)
        if sealed_cache_key in self._parsed_sealed_cache:
            self._parsed_sealed_cache.move_to_end(sealed_cache_key)
            sealed_dicts = copy.deepcopy(self._parsed_sealed_cache[sealed_cache_key])
        else:
            sealed_dicts = parser.parse_sealed_products(config, self.client)
            self._cache_parsed(self._parsed_sealed_cache, sealed_cache_key, sealed_dicts)

        # Step 3: Build DTO
        dto = self.dto_builder.build(config, card_dicts, sealed_dicts)
        
        # Step 4: Convert to payload
        payload = dto.model_dump()
        if self.enable_db_ingestion and not self.target_market_date:
            raise RuntimeError("DB-enabled scrape requires an immutable target_market_date")
        for card in payload.get('data', {}).get('cards', []):
            card['_market_date'] = self.target_market_date
        for sealed_product in payload.get('data', {}).get('sealed_products', []):
            # Sealed observations use the same immutable Phoenix market date as
            # card observations. Wall-clock UTC previously mislabeled late
            # local runs as the following day.
            sealed_product['_market_date'] = self.target_market_date
        parse_report = dict(getattr(parser, 'last_card_parse_report', {}) or {})
        diagnostic_names = {
            "raw_rows": "rawRows", "commercial_products": "commercialProducts",
            "source_variant_groups": "sourceVariantGroups",
            "accepted_variant_groups": "acceptedVariantGroups",
            "rejected_ambiguous_variant_groups": "rejectedAmbiguousVariantGroups",
            "rejected_missing_nm_variant_groups": "rejectedMissingNmVariantGroups",
            "rejected_external_variant_identity_unavailable": "rejectedExternalVariantIdentityUnavailable",
            "accepted_market_only_ambiguous_variant_groups": "acceptedMarketOnlyAmbiguousVariantGroups",
            "accepted_exact_variant_groups": "acceptedExactVariantGroups",
            "dropped_no_market_price": "droppedNoMarketPrice",
        }
        parse_diagnostics = {diagnostic_names.get(key, key): value
                             for key, value in parse_report.items()}
        source_variant_keys = sorted({
            f"{card.get('tcgplayer_product_id')}|{card.get('external_variant_key')}"
            for card in payload.get('data', {}).get('cards', [])
            if card.get('tcgplayer_product_id') and card.get('external_variant_key')
        })
        outcome = {"payloadCards": len(payload.get('data', {}).get('cards', [])),
                   "ingestionAttempted": False, "ingestionSuccess": not self.enable_db_ingestion,
                   "setId": None, "priceRowsAttempted": 0, "priceRowsInserted": 0,
                   "priceRowsUpdated": 0, "priceRowsSkippedDuplicates": 0,
                   "ingestionErrors": [], "sourceVariantKeys": source_variant_keys,
                   "marketDate": self.target_market_date,
                   "responseProvenance": provenance_report,
                   **parse_diagnostics}

        _payload_cards = len(payload.get('data', {}).get('cards', []))
        print(
            f"[DIAG][{config.SET_NAME}] step=payload "
            f"cards_in_payload={_payload_cards}"
        )

        # Debug output
        print(f"\n[OK] Payload created:")
        data = payload.get('data', {})
        print(f"  - Set: {data.get('gameContext', {}).get('set', 'N/A')}")
        print(f"  - Cards: {len(data.get('cards', []))}")
        print(f"  - Sealed Products: {len(data.get('sealed_products', []))}")
        
        with open('payload_debug.json', 'w') as f:
            json.dump(payload, f, indent=2)
        
        # Step 5: Ingest to database (if enabled)
        if self.enable_db_ingestion:
            outcome["ingestionAttempted"] = True
            print("\n[SEND] Sending data to database...")
            try:
                # Payload already has the correct structure with type and data fields
                result = self.ingest_controller.ingest(payload)
                if result and result.get('success'):
                    cards_detail = result.get('details', {}).get('cards', {})
                    sealed_detail = result.get('details', {}).get('sealed_products', {})
                    summary = result.get('summary', {})
                    outcome.update(validate_ingestion_result(payload, result))
                    def _metric_count(value):
                        """Return a count from a metric that may be int, list, or None."""
                        if isinstance(value, (int, float)):
                            return int(value)
                        if isinstance(value, (list, tuple, dict, set, str)):
                            return len(value)
                        return 0

                    _set_id = result.get('set_id')
                    _cards_inserted = result.get('details', {}).get('cards', {}).get('inserted_cards', 0)
                    _cards_reused = _metric_count(result.get('details', {}).get('cards', {}).get('ingestion_efficiency', {}).get('attempted_rows'))
                    print(
                        f"[DIAG][{config.SET_NAME}] step=ingest "
                        f"set_id={_set_id} "
                        f"cards_inserted={_cards_inserted}"
                    )
                    print("[OK] Database ingestion successful")
                    print(f"\n[SUMMARY] Ingestion Summary:")
                    if 'summary' in result:
                        payload['_ingestion_efficiency'] = result['summary']
                        for key, value in result['summary'].items():
                            print(f"   {key}: {value}")
                else:
                    raise RuntimeError(f"Database ingestion failed: {(result or {}).get('error', 'Unknown error')}")
            except Exception as e:
                print(f"[ERROR] Database ingestion failed: {e}")
                import traceback
                traceback.print_exc()
                outcome["ingestionErrors"].append(str(e))
                payload['_scrape_outcome'] = outcome
                raise
        
        # Step 6: Optional - Save to Excel
        # save_to_excel(card_dicts, sealed_dicts, excel_path)
        
        payload['_scrape_outcome'] = outcome
        return payload

    def get_request_metrics(self):
        return self.client.get_metrics()

def validate_ingestion_result(payload, result):
    if not result or not result.get('success'):
        raise RuntimeError(f"Database ingestion failed: {(result or {}).get('error', 'Unknown error')}")
    cards_detail = result.get('details', {}).get('cards', {})
    sealed_detail = result.get('details', {}).get('sealed_products', {})
    errors = list(cards_detail.get('errors') or [])
    error_codes = list(cards_detail.get('error_codes') or [])
    efficiency = cards_detail.get('ingestion_efficiency', {})
    priced = any((card.get('prices') or {}).get('market') is not None
                 for card in payload.get('data', {}).get('cards', []))
    if errors:
        if ERROR_EXTERNAL_VARIANT_IDENTITY_CONFLICT in error_codes:
            raise ExternalVariantIdentityConflict(f"Fatal card ingestion errors: {errors[:5]}")
        raise RuntimeError(f"Fatal card ingestion errors: {errors[:5]}")
    if priced and int(efficiency.get('attempted_rows', 0)) == 0:
        raise RuntimeError("Priced payload produced zero attempted price rows")
    sealed_errors = list(sealed_detail.get('errors') or [])
    sealed_efficiency = sealed_detail.get('ingestion_efficiency', {})
    sealed_priced = any((product.get('prices') or {}).get('market') is not None
                        for product in payload.get('data', {}).get('sealed_products', []))
    if sealed_errors:
        raise RuntimeError(f"Fatal sealed ingestion errors: {sealed_errors[:5]}")
    if sealed_priced and int(sealed_efficiency.get('attempted_rows', 0)) == 0:
        raise RuntimeError("Priced sealed payload produced zero attempted price rows")
    persistence = cards_detail.get('persistence_metrics') or efficiency.get('persistence_metrics') or {}
    return {"setId": result.get('set_id'),
            "priceRowsAttempted": int(efficiency.get('attempted_rows', 0)),
            "priceRowsInserted": int(efficiency.get('inserted_rows', 0)),
            "priceRowsUpdated": int(cards_detail.get('price_rows_updated', 0)),
            "priceRowsSkippedDuplicates": int(efficiency.get('skipped_duplicates', 0)),
            "sealedRowsAttempted": int(sealed_efficiency.get('attempted_rows', 0)),
            "sealedRowsInserted": int(sealed_efficiency.get('inserted_rows', 0)),
            "sealedRowsUpdated": int(sealed_efficiency.get('updated_rows', 0)),
            "sealedRowsSkippedDuplicates": int(sealed_efficiency.get('skipped_duplicates', 0)),
            **persistence, "ingestionErrors": [], "ingestionSuccess": True}
