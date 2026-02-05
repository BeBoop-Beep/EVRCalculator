from ...clients.tcgplayer_client import TCGPlayerClient
from ...parsers.tcgplayer_parser import TCGPlayerParser
from ..dto_builders.tcgplayer_dto_builder import TCGPlayerDTOBuilder
from ...exporters.excel_writer import save_to_excel
import json
import sys
import os

# Add path to import from db folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db.services.ingest_service import IngestService

class TCGScraper:
    def __init__(self, enable_db_ingestion=False):
        self.client = TCGPlayerClient()
        self.dto_builder = TCGPlayerDTOBuilder()
        self.enable_db_ingestion = enable_db_ingestion
        if enable_db_ingestion:
            self.ingest_service = IngestService()
    
    def scrape(self, config, excel_path):
        """Main scraping workflow"""
        
        # Step 1: Fetch raw data
        raw_data = self.client.fetch_price_data(config.CARD_DETAILS_URL)
       
        # Step 2: Parse data
        parser = TCGPlayerParser(config.PULL_RATE_MAPPING)
        card_dicts = parser.parse_cards(raw_data)
        sealed_dicts = parser.parse_sealed_products(config, self.client)

        # Step 3: Build DTO
        dto = self.dto_builder.build(config, card_dicts, sealed_dicts)
        
        # Step 4: Convert to payload
        payload = dto.model_dump()
        
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
            print("\n[SEND] Sending data to database...")
            try:
                # Extract data directly and pass to service (bypass controller)
                data = payload.get('data', {})
                result = self.ingest_service.ingest(data)
                if result and result.get('success'):
                    print("[OK] Database ingestion successful")
                    print(f"\n[SUMMARY] Ingestion Summary:")
                    if 'details' in result:
                        for key, value in result['details'].items():
                            print(f"   {key}: {value}")
                else:
                    print(f"[WARN] Database ingestion failed: {result.get('error', 'Unknown error')}")
            except Exception as e:
                print(f"[ERROR] Database ingestion failed: {e}")
                import traceback
                traceback.print_exc()
                # Don't raise - continue with the rest of the workflow
        
        # Step 6: Optional - Save to Excel
        # save_to_excel(card_dicts, sealed_dicts, excel_path)
        
        return payload

