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

    def scrape(self, config, excel_path, set_name):

        raw_card_data = self.client.fetch_price_data(config.CARD_DETAILS_URL)
        raw_sealed_data = self.client.fetch_price_data(config.SEALED_DETAILS_URL)

        print(raw_sealed_data)

        parser = TCGPlayerParser(config.PULL_RATE_MAPPING)
        card_dicts = parser.parse_cards(raw_card_data)
        sealed_dicts = parser.parse_sealed_products(config.SEALED_DETAILS_URL, self.client, set_name)

        # Build DTO objects
        dto = TCGPlayerIngestDTO(
            set=SetDTO(
                name=set_name,
                abbreviation=config.SET_ABBREVIATION,
                tcg=getattr(config.TCG, 'TCG', None)
            ),
            cards=[CardDTO(**c) for c in card_dicts],
            sealed_products=[SealedProductDTO(**s) for s in sealed_dicts],
            source="TCGPLAYER"
        )

        # Now send dto.json() to your ingest endpoint
        payload = dto.model_dump()

        # Excel writing stays as-is for now
        # save_to_excel(card_dicts, sealed_dicts, excel_path)

        return payload

            
