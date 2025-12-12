import json
from ..clients.tcgplayer_client import TCGPlayerClient
from ..parsers.tcgplayer_parser import TCGPlayerParser
from ..exporters.excel_writer import save_to_excel
from ..dtos.ingest_dto import (
    TCGPlayerIngestDTO,
    CardDTO,
    SealedProductDTO,
    SetDTO
)

class TCGScraper:
    def __init__(self):
        self.client = TCGPlayerClient()

    def scrape(self, config, excel_path):

        raw_card_data = self.client.fetch_price_data(config.CARD_DETAILS_URL)


        parser = TCGPlayerParser(config.PULL_RATE_MAPPING)
        card_dicts = parser.parse_cards(raw_card_data)
        sealed_dicts = parser.parse_sealed_products(config, self.client, config.SET_NAME) 

        # Build DTO objects
        try:
            set_dto = SetDTO(
                name=config.SET_NAME,
                abbreviation=config.SET_ABBREVIATION,
                tcg=getattr(config, 'TCG', 'Pokemon')  # Default to 'Pokemon' if not set
            )
            
            dto = TCGPlayerIngestDTO(
                set=set_dto,
                cards=[CardDTO(**c) for c in card_dicts],
                sealed_products=[SealedProductDTO(**s) for s in sealed_dicts],
                source="TCGPLAYER"
            )
            
            payload = dto.model_dump()
        
        except Exception as e:
            print(f"❌ Error creating DTO: {e}")
            print(f"Debug - config.TCG: {getattr(config, 'TCG', 'NOT SET')}")
            print(f"Debug - set_name: {config.SET_NAME}")
            print(f"Debug - config.SET_ABBREVIATION: {config.SET_ABBREVIATION}")
            raise

        # #DEBUGGING PURPOSES
        # # Debug: Print summary
        # print(f"\n✅ Payload created:")
        # print(f"🔍 Payload keys: {list(payload.keys())}")  # See what keys actually exist
        # print(f"🔍 Full payload structure:\n{json.dumps(payload, indent=2)[:1000]}")  # First 1000 chars
        
        # # Check if 'set' exists before accessing
        # if 'set' in payload:
        #     print(f"  - Set: {payload['set']['name']} ({payload['set']['abbreviation']})")
        # else:
        #     print(f"  ⚠️ 'set' key not found in payload!")
        #     print(f"  Available keys: {list(payload.keys())}")
        
        # print(f"  - Cards: {len(payload.get('cards', []))}")
        # print(f"  - Sealed Products: {len(payload.get('sealed_products', []))}")
        # print(f"  - Source: {payload.get('source', 'N/A')}")

        # with open('payload_debug.json', 'w') as f:
        #     json.dump(payload, f, indent=2)
        # print("  - Debug payload saved to payload_debug.json")

            # Excel writing stays as-is for now
            # save_to_excel(card_dicts, sealed_dicts, excel_path)

        return payload


