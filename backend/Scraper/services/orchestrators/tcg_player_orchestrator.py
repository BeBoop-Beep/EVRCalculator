from ...clients.tcgplayer_client import TCGPlayerClient
from ...parsers.tcgplayer_parser import TCGPlayerParser
from ..dto_builders.tcgplayer_dto_builder import TCGPlayerDTOBuilder
from backend.db.controllers.ingest_controller import IngestController
from collections import OrderedDict
import copy
import json
import sys
import os

# Add path to import from db folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))


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
        _raw_count = len(raw_data.get("result", []))
        print(
            f"[DIAG][{config.SET_NAME}] step=fetch "
            f"raw_cards={_raw_count} "
            f"url={config.CARD_DETAILS_URL}"
        )

        # Step 2: Parse data
        parser = TCGPlayerParser(config.PULL_RATE_MAPPING)
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
        parse_report = dict(getattr(parser, 'last_card_parse_report', {}) or {})
        diagnostic_names = {
            "raw_rows": "rawRows", "commercial_products": "commercialProducts",
            "source_variant_groups": "sourceVariantGroups",
            "accepted_variant_groups": "acceptedVariantGroups",
            "rejected_ambiguous_variant_groups": "rejectedAmbiguousVariantGroups",
            "rejected_missing_nm_variant_groups": "rejectedMissingNmVariantGroups",
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
    errors = list(cards_detail.get('errors') or [])
    efficiency = cards_detail.get('ingestion_efficiency', {})
    priced = any((card.get('prices') or {}).get('market') is not None
                 for card in payload.get('data', {}).get('cards', []))
    if errors:
        raise RuntimeError(f"Fatal card ingestion errors: {errors[:5]}")
    if priced and int(efficiency.get('attempted_rows', 0)) == 0:
        raise RuntimeError("Priced payload produced zero attempted price rows")
    return {"setId": result.get('set_id'),
            "priceRowsAttempted": int(efficiency.get('attempted_rows', 0)),
            "priceRowsInserted": int(efficiency.get('inserted_rows', 0)),
            "priceRowsUpdated": int(cards_detail.get('price_rows_updated', 0)),
            "priceRowsSkippedDuplicates": int(efficiency.get('skipped_duplicates', 0)),
            "ingestionErrors": [], "ingestionSuccess": True}
