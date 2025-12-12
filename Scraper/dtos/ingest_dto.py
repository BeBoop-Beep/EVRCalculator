from pydantic import BaseModel
from typing import List, Optional, Dict

class SetDTO(BaseModel):
    name: str
    abbreviation: Optional[str]
    tcg: Optional[str]  # Pokemon, Magic, Yu-Gi-Oh, etc.


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
    set: SetDTO
    cards: List[CardDTO]
    sealed_products: List[SealedProductDTO]
    source: str
