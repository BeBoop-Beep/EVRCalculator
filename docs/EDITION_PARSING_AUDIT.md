# TCGPlayer Printing Parser Implementation - End-to-End Audit

## Overview
This document traces the flow of vintage edition data (e.g., "1st Edition", "Unlimited") through the entire scraper pipeline to ensure preservation of edition semantics in the database.

## Data Flow Tracing

### 1. **Raw TCGPlayer Data** 
Source: TCGPlayer API response
```json
{
  "productName": "Dark Omanyte - 037/105",
  "number": "037/105",
  "printing": "1st Edition",
  "condition": "Moderately Played 1st Edition",
  "rarity": "Uncommon",
  "marketPrice": 4.65
}
```

### 2. **Scraper Entry Point** (`backend/Scraper/services/orchestrators/tcg_player_orchestrator.py`)
- `TCGScraper.scrape(config, excel_path)` is the main entry point
- Calls `TCGPlayerParser.parse_cards(raw_data)` with raw API response
- Calls `TCGPlayerDTOBuilder.build(config, card_dicts, sealed_dicts)` with parsed cards
- Builds payload via `dto.model_dump()`
- **Flow preserves payload structure** ✓

### 3. **Parser Stage** (`backend/Scraper/parsers/tcgplayer_parser.py`)

#### Step 3a: `TCGPlayerParser.parse_cards()`
- Calls `process_card()` from `card_helper.py` for each raw card
- Creates unique key for deduplication (includes `printing`)
- Returns list of processed card dictionaries
- **`printing` field preserved in card_dict** ✓

#### Step 3b: `process_card()` in `card_helper.py` (UPDATED)
- **NEW**: Calls `parse_tcgplayer_printing(printing)` 
- Returns `(edition, printing_type)` tuple:
  - "1st Edition" → ("1st-edition", "non-holo")
  - "Unlimited" → ("unlimited", "non-holo")
  - "1st Edition Holofoil" → ("1st-edition", "holo")
  - "Unlimited Holofoil" → ("unlimited", "holo")
- Adds `edition` and `printing_type` to `card_dict`
- **`edition` and `printing_type` now in card_dict** ✓

#### Step 3c: `_clean_card_data()` in `TCGPlayerParser` (UPDATED)
- Iterates over cards from `parse_cards()`
- **NEW**: Propagates `edition` and `printing_type` fields
- Builds `cleaned_card` with:
  ```python
  'edition': (card.get('edition') or '').strip(),
  'printing_type': (card.get('printing_type') or '').strip(),
  ```
- Also preserves `printing` for backward compatibility
- Returns list of cleaned card dicts
- **Fields propagated to cleaned cards list** ✓

### 4. **DTO Builder Stage** (`backend/Scraper/services/dto_builders/tcgplayer_dto_builder.py`)
- `TCGPlayerDTOBuilder.build(config, card_dicts, sealed_dicts)`
- Creates `CardDTO(**card)` for each card dict
- **Flow does not filter fields** - all dict fields pass to DTO constructor
- **All fields flow to CardDTO** ✓

### 5. **DTO Model** (`backend/Scraper/dtos/ingest_dto.py`)

#### `CardDTO` Model (UPDATED)
```python
class CardDTO(BaseModel):
    name: str
    card_number: Optional[str]
    rarity: Optional[str]
    variant: Optional[str]
    condition: Optional[str] = None
    printing: Optional[str] = None
    edition: Optional[str] = None  # NEW
    printing_type: Optional[str] = None  # NEW
    pull_rate: Optional[float]
    prices: Dict[str, Optional[float]]
    source: Optional[str] = None
    currency: Optional[str] = None
```

- Pydantic `ConfigDict(extra='ignore')` allows extra fields but ignores unknowns
- **`edition` and `printing_type` fields now defined** ✓

### 6. **Payload Serialization** (`tcg_player_orchestrator.py`)
- `payload = dto.model_dump()` converts DTO to dict
- `TCGPlayerIngestDTO.model_dump()` returns payload structure:
  ```python
  {
    'type': 'pokemon',
    'data': {
      'collection': {...},
      'gameContext': {...},
      'cards': [
        {
          'name': 'Dark Omanyte',
          'card_number': '037/105',
          'condition': 'Moderately Played',
          'edition': '1st-edition',  # ← PRESERVED
          'printing_type': 'non-holo',  # ← PRESERVED
          'printing': '1st Edition',  # ← PRESERVED
          'rarity': 'Uncommon',
          'variant': None,
          'pull_rate': 2.0,
          'prices': {'market': 4.65},
          'source': 'TCGPlayer',
          'currency': 'USD'
        }
      ],
      'sealed_products': []
    },
    'source': 'TCGPLAYER'
  }
  ```
- **Payload includes `edition` and `printing_type`** ✓

### 7. **Ingest Pipeline** (`backend/db/controllers/ingest_controller.py`)
- `IngestController.ingest(payload)` validates and routes payload
- Routes to `IngestService.ingest(data)` with `payload['data']`
- **Payload structure preserved** ✓

### 8. **TCG Orchestration** (`backend/db/services/orchestrators/tcg_orchestrator.py`)
- `TCGOrchestrator.ingest(data)` routes to `PokemonTCGOrchestrator.ingest(data)`
- **Payload structure preserved** ✓

### 9. **Card Processing** (`backend/db/services/cards_service.py`)

#### `_extract_variant_info()` (UPDATED)
```python
def _extract_variant_info(self, card):
    variant = card.get('variant')
    
    # NEW: Use parsed fields if available
    parsed_printing_type = (card.get('printing_type') or '').strip().lower()
    parsed_edition = (card.get('edition') or '').strip().lower()
    
    if parsed_printing_type:
        printing_type = parsed_printing_type
    else:
        # Fallback to old logic if not parsed upstream
        printing = (card.get('printing') or '').strip().lower()
        printing_type = 'non-holo'
        if 'holofoil' in printing or 'holo' in printing:
            if 'reverse' in printing:
                printing_type = 'reverse-holo'
            else:
                printing_type = 'holo'
    
    # NEW: Use parsed edition
    edition = parsed_edition if parsed_edition else None
    
    special_type = variant if variant else None
    
    return printing_type, special_type, edition
```

- **Method now extracts both `edition` and `printing_type` from payload** ✓
- **Supports both new parsed fields AND fallback to old logic** ✓

### 10. **Database Insertion** (`backend/db/repositories/card_variant_repository.py`)
- `insert_card_variant()` or `insert_card_variants_batch()` inserts into `card_variants` table
- Schema columns:
  ```sql
  CREATE TABLE card_variants (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL,
    printing_type VARCHAR(50),
    special_type VARCHAR(50),
    edition VARCHAR(50),
    ...
  )
  ```
- Batch insert includes:
  ```python
  'printing_type': printing_type,
  'special_type': special_type,
  'edition': edition,
  ```
- **`edition` and `printing_type` stored in database** ✓

## Summary

✓ **Complete end-to-end data flow preserved**

| Stage | Component | Status | Notes |
|-------|-----------|--------|-------|
| 1 | Raw API Data | ✓ | `printing` field from TCGPlayer |
| 2 | Parser | ✓ | `parse_tcgplayer_printing()` extracts edition + printing_type |
| 3 | Card Processing | ✓ | `process_card()` adds `edition` and `printing_type` to card_dict |
| 4 | Cleaned Data | ✓ | `_clean_card_data()` propagates fields |
| 5 | DTO Model | ✓ | `CardDTO` includes `edition` and `printing_type` fields |
| 6 | Payload | ✓ | `model_dump()` serializes all fields |
| 7 | Ingestion | ✓ | Fields pass through controller/service pipeline |
| 8 | Variant Extraction | ✓ | `_extract_variant_info()` uses parsed fields with fallback |
| 9 | Database | ✓ | `card_variants.edition` and `card_variants.printing_type` populated |

## Backward Compatibility

- Original `printing` field is **preserved** for backward compatibility
- If parsing fails upstream, `_extract_variant_info()` falls back to old parsing logic from raw `printing` field
- Existing code that doesn't parse edition still works (defaults to `None`)
- No breaking changes to schema or API

## Test Coverage

### Unit Tests (15 tests pass)
- `test_card_helper.py::TestParseTCGPlayerPrinting` - 15 tests
  - Covers all mappings: 1st Edition, Unlimited, Holofoil, Reverse Holofoil
  - Case insensitivity, whitespace handling, None/empty inputs

### Integration Tests (7 tests pass)
- `test_tcgplayer_parser_dto.py::TestTCGPlayerParserEditionParsing` - 5 tests
  - Full flow from raw TCGPlayer data to cleaned cards
  - Verifies `edition` and `printing_type` in final payload
- `test_tcgplayer_parser_dto.py::TestCardDTOWithEditionAndPrintingType` - 2 tests
  - CardDTO accepts and preserves new fields

## Bug Fix Impact

**Before Fix:**
- "1st Edition" and "Unlimited" cards collapsed into same variant
- `edition` field was always `None` in database
- Vintage edition semantics lost

**After Fix:**
- "1st Edition" → `edition="1st-edition"`, `printing_type="non-holo"`
- "Unlimited" → `edition="unlimited"`, `printing_type="non-holo"`
- "1st Edition Holofoil" → `edition="1st-edition"`, `printing_type="holo"`
- "Unlimited Holofoil" → `edition="unlimited"`, `printing_type="holo"`
- **Each variant correctly stored with proper edition semantics**

## Conclusion

The fix successfully preserves TCGplayer vintage edition information through the entire ingestion pipeline with:
- ✓ No breaking changes
- ✓ Full backward compatibility
- ✓ Comprehensive test coverage
- ✓ Clean separation of concerns (parsing in helper, propagation through layers, extraction at database boundary)
