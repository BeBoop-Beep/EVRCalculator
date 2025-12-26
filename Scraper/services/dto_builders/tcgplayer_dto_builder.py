from typing import List, Dict
from ...dtos.ingest_dto import (
    CollectionDTO,
    TCGPlayerIngestDTO,
    GameContextDTO,
    CardDTO,
    SealedProductDTO
)

class TCGPlayerDTOBuilder:
    """Builds TCGPlayer-specific DTOs from parsed data"""
    
    @staticmethod
    def build(config, card_dicts: List[Dict], sealed_dicts: List[Dict]) -> TCGPlayerIngestDTO:
        """
        Build TCGPlayerIngestDTO from parsed data
        
        Args:
            config: Set configuration object
            card_dicts: List of parsed card dictionaries
            sealed_dicts: List of parsed sealed product dictionaries
            
            
        Returns:
            TCGPlayerIngestDTO: Complete DTO ready for ingestion
        """
        set_name = config.SET_NAME

        collection_dto = CollectionDTO(
            name=getattr(config, 'COLLECTION', None)
        )

        # Build GameContextDTO
        gamecontext_dto = GameContextDTO(
            name=set_name,
            abbreviation=getattr(config, 'SET_ABBREVIATION', None),
            tcg=getattr(config, 'TCG', None),
            era=getattr(config, 'ERA', None),
        )
        
        # Build CardDTO list
        card_dtos = [CardDTO(**card) for card in card_dicts]
        
        # Build SealedProductDTO list
        sealed_dtos = [SealedProductDTO(**product) for product in sealed_dicts]
        
        # Build main DTO
        return TCGPlayerIngestDTO(
            collection=collection_dto,
            game_context=gamecontext_dto,
            cards=card_dtos,
            sealed_products=sealed_dtos,
            source="TCGPLAYER"
        )