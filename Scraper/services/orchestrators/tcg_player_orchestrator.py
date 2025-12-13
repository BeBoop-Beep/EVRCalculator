from ...clients.tcgplayer_client import TCGPlayerClient
from ...parsers.tcgplayer_parser import TCGPlayerParser
from ..dto_builders.tcgplayer_dto_builder import TCGPlayerDTOBuilder
from ...exporters.excel_writer import save_to_excel
import json
import sys
import os

# Add path to import from db folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))
from db.controllers.ingest_controller import IngestController

class TCGScraper:
    def __init__(self, enable_db_ingestion=False):
        self.client = TCGPlayerClient()
        self.dto_builder = TCGPlayerDTOBuilder()
        self.enable_db_ingestion = enable_db_ingestion
        if enable_db_ingestion:
            self.ingest_controller = IngestController()
    
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
        print(f"\n✅ Payload created:")
        print(f"  - Set: {payload.get('set', {}).get('name', 'N/A')}")
        print(f"  - Cards: {len(payload.get('cards', []))}")
        print(f"  - Sealed Products: {len(payload.get('sealed_products', []))}")
        
        with open('payload_debug.json', 'w') as f:
            json.dump(payload, f, indent=2)
        
        # Step 5: Ingest to database (if enabled)
        if self.enable_db_ingestion:
            print("\n📤 Sending data to database...")
            try:
                result = self.ingest_controller.ingest(payload)
                if result and result.get('success'):
                    print("✅ Database ingestion successful")
                else:
                    print(f"⚠️ Database ingestion failed: {result.get('error', 'Unknown error')}")
            except Exception as e:
                print(f"❌ Database ingestion failed: {e}")
                # Don't raise - continue with the rest of the workflow
        
        # Step 6: Optional - Save to Excel
        # save_to_excel(card_dicts, sealed_dicts, excel_path)
        
        return payload

