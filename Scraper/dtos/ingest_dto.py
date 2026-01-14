from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict

# This is currently for a Pokemon type DTO, 
# we will need a sorter later that creates 
# specific DTO's per collection and even TCG type.
class CollectionDTO(BaseModel):
    model_config = ConfigDict(extra='ignore')
    name: str 

class GameContextDTO(BaseModel):
    """Contains game context metadata (TCG type, era, etc) - works for any product type"""
    model_config = ConfigDict(extra='ignore')
    set: str
    abbreviation: Optional[str]
    tcg: Optional[str]  # Pokemon, Magic, Yu-Gi-Oh, etc.
    era: Optional[str]  # Base, Neo, etc. (optional for non-TCG products)

class CardDTO(BaseModel):
    """Card data DTO - explicitly ignores unknown fields like copies_in_pack"""
    model_config = ConfigDict(extra='ignore')
    name: str
    card_number: Optional[str]
    rarity: Optional[str]
    variant: Optional[str]
    condition: Optional[str] = None  # Card condition (Near Mint, Lightly Played, etc.)
    printing: Optional[str] = None  # Printing type or edition info
    pull_rate: Optional[float]
    prices: Dict[str, Optional[float]]  # market, low, reverse, etc.
    source: Optional[str] = None  # e.g., 'TCGPlayer'
    currency: Optional[str] = None  # defaults to USD if not provided

class SealedProductDTO(BaseModel):
    model_config = ConfigDict(extra='ignore')
    name: str
    product_type: str           # booster box, ETB, etc.
    prices: Dict[str, Optional[float]]
    source: Optional[str] = None  # e.g., 'TCGPlayer'
    currency: Optional[str] = None  # defaults to USD if not provided

class TCGPlayerIngestDTO(BaseModel):
    type: str  # e.g., 'pokemon', 'magic', 'yugioh' - determined by TCG type
    collection: CollectionDTO
    gameContext: GameContextDTO
    cards: List[CardDTO]
    sealed_products: List[SealedProductDTO]
    source: str

    def model_dump(self, **kwargs):
        """Override model_dump to return payload in format expected by IngestController"""
        # Ensure mode='python' to properly serialize nested Pydantic models
        if 'mode' not in kwargs:
            kwargs['mode'] = 'python'
        data_dict = super().model_dump(**kwargs)
        return {
            'type': data_dict['type'],
            'data': {
                'collection': data_dict['collection'],
                'gameContext': data_dict['gameContext'],
                'set': data_dict['gameContext'],  # Database schema expects 'set' key
                'cards': data_dict['cards'],
                'sealed_products': data_dict['sealed_products'],
            },
            'source': data_dict['source']
        }
