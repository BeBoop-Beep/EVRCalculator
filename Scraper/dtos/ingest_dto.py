from pydantic import BaseModel
from typing import List, Optional, Dict

class CardDTO(BaseModel):
    name: str
    set_name: str
    card_number: Optional[str]
    rarity: Optional[str]
    variant: Optional[str]
    pull_rate: Optional[float]
    prices: Dict[str, Optional[float]]  # market, low, reverse, etc.
    source: str

class SealedProductDTO(BaseModel):
    name: str
    set_name: Optional[str]
    product_type: str           # booster box, ETB, etc.
    prices: Dict[str, Optional[float]]
    source: str

class TCGPlayerIngestDTO(BaseModel):
    cards: List[CardDTO]
    sealed_products: List[SealedProductDTO]
    source: str = "TCGPLAYER"
