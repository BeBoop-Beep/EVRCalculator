from pydantic import BaseModel
from typing import List, Optional, Dict

# This is currently for a Pokemon type DTO, 
# we will need a sorter later that creates 
# specific DTO's per collection and even TCG type.
class CollectionDTO(BaseModel):
    name: str 

class GameContextDTO(BaseModel):
    """Contains game context metadata (TCG type, era, etc) - works for any product type"""
    name: str
    abbreviation: Optional[str]
    tcg: Optional[str]  # Pokemon, Magic, Yu-Gi-Oh, etc.
    era: Optional[str]  # Base, Neo, etc. (optional for non-TCG products)

class CardDTO(BaseModel):
    name: str
    card_number: Optional[str]
    rarity: Optional[str]
    variant: Optional[str]
    pull_rate: Optional[float]
    prices: Dict[str, Optional[float]]  # market, low, reverse, etc.

class SealedProductDTO(BaseModel):
    name: str
    product_type: str           # booster box, ETB, etc.
    prices: Dict[str, Optional[float]]

class TCGPlayerIngestDTO(BaseModel):
    collection: CollectionDTO
    set: GameContextDTO
    cards: List[CardDTO]
    sealed_products: List[SealedProductDTO]
    source: str
