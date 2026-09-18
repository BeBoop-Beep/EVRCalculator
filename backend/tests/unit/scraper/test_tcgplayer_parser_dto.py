"""
Integration tests for TCGPlayer parser and DTO builder, focusing on edition/printing_type parsing.
"""

import pytest
from backend.Scraper.parsers.tcgplayer_parser import TCGPlayerParser
from backend.Scraper.services.dto_builders.tcgplayer_dto_builder import TCGPlayerDTOBuilder
from backend.Scraper.dtos.ingest_dto import CardDTO


class TestTCGPlayerParserEditionParsing:
    """Integration tests for parser with edition/printing_type parsing"""
    
    @pytest.fixture
    def parser(self):
        """Create a TCGPlayerParser instance with minimal pull rate mapping"""
        pull_rate_mapping = {
            'Common': 1,
            'Uncommon': 2,
            'Rare': 3,
        }
        return TCGPlayerParser(pull_rate_mapping)
    
    def test_parse_1st_edition_card(self, parser):
        """Test parsing a 1st Edition vintage card"""
        raw_data = {
            "result": [
                {
                    "productName": "Dark Omanyte - 037/105",
                    "number": "037/105",
                    "printing": "1st Edition",
                    "condition": "Near Mint 1st Edition",
                    "rarity": "Uncommon",
                    "marketPrice": 4.65
                }
            ]
        }
        
        # Pull rate mapping needed
        parser.pull_rate_mapping = {
            'Common': 1,
            'Uncommon': 2,
            'Rare': 3,
        }
        
        cleaned_cards = parser.parse_cards(raw_data)
        
        assert len(cleaned_cards) == 1
        card = cleaned_cards[0]
        
        # Verify core fields
        assert card['name'] == "Dark Omanyte"
        assert card['card_number'] == "037/105"
        assert card['condition'] == "Near Mint"
        
        # Verify parsed edition and printing_type
        assert card['edition'] == "1st-edition"
        assert card['printing_type'] == "non-holo"
        
        # Verify raw printing preserved
        assert card['printing'] == "1st Edition"
    
    def test_parse_unlimited_card(self, parser):
        """Test parsing an Unlimited vintage card"""
        raw_data = {
            "result": [
                {
                    "productName": "Alakazam - 001/102",
                    "number": "001/102",
                    "printing": "Unlimited",
                    "condition": "Near Mint Unlimited",
                    "rarity": "Rare",
                    "marketPrice": 15.50
                }
            ]
        }
        
        parser.pull_rate_mapping = {
            'Common': 1,
            'Uncommon': 2,
            'Rare': 3,
        }
        
        cleaned_cards = parser.parse_cards(raw_data)
        
        assert len(cleaned_cards) == 1
        card = cleaned_cards[0]
        
        assert card['name'] == "Alakazam"
        assert card['card_number'] == "001/102"
        assert card['condition'] == "Near Mint"
        
        # Verify parsed edition and printing_type
        assert card['edition'] == "unlimited"
        assert card['printing_type'] == "non-holo"
    
    def test_parse_1st_edition_holofoil_card(self, parser):
        """Test parsing a 1st Edition Holofoil vintage card"""
        raw_data = {
            "result": [
                {
                    "productName": "Charizard - 004/102",
                    "number": "004/102",
                    "printing": "1st Edition Holofoil",
                    "condition": "Near Mint 1st Edition Holofoil",
                    "rarity": "Rare",
                    "marketPrice": 250.00
                }
            ]
        }
        
        parser.pull_rate_mapping = {
            'Common': 1,
            'Uncommon': 2,
            'Rare': 3,
        }
        
        cleaned_cards = parser.parse_cards(raw_data)
        
        assert len(cleaned_cards) == 1
        card = cleaned_cards[0]
        
        assert card['name'] == "Charizard"
        assert card['card_number'] == "004/102"
        assert card['condition'] == "Near Mint"
        
        # Verify parsed edition and printing_type
        assert card['edition'] == "1st-edition"
        assert card['printing_type'] == "holo"
    
    def test_parse_unlimited_holofoil_card(self, parser):
        """Test parsing an Unlimited Holofoil vintage card"""
        raw_data = {
            "result": [
                {
                    "productName": "Blastoise - 002/102",
                    "number": "002/102",
                    "printing": "Unlimited Holofoil",
                    "condition": "Near Mint Unlimited Holofoil",
                    "rarity": "Rare",
                    "marketPrice": 45.00
                }
            ]
        }
        
        parser.pull_rate_mapping = {
            'Common': 1,
            'Uncommon': 2,
            'Rare': 3,
        }
        
        cleaned_cards = parser.parse_cards(raw_data)
        
        assert len(cleaned_cards) == 1
        card = cleaned_cards[0]
        
        assert card['name'] == "Blastoise"
        assert card['card_number'] == "002/102"
        assert card['condition'] == "Near Mint"
        
        # Verify parsed edition and printing_type
        assert card['edition'] == "unlimited"
        assert card['printing_type'] == "holo"
    
    def test_parse_reverse_holofoil_card(self, parser):
        """Test parsing a Reverse Holofoil card (no edition)"""
        raw_data = {
            "result": [
                {
                    "productName": "Pikachu - 025/102",
                    "number": "025/102",
                    "printing": "Reverse Holofoil",
                    "condition": "Near Mint Reverse Holofoil",
                    "rarity": "Common",
                    "marketPrice": 5.00
                }
            ]
        }
        
        parser.pull_rate_mapping = {
            'Common': 1,
            'Uncommon': 2,
            'Rare': 3,
        }
        
        cleaned_cards = parser.parse_cards(raw_data)
        
        assert len(cleaned_cards) == 1
        card = cleaned_cards[0]
        
        assert card['name'] == "Pikachu"
        assert card['card_number'] == "025/102"
        
        # Verify parsed edition and printing_type (no edition for reverse holo)
        assert card['edition'] == ""
        assert card['printing_type'] == "reverse-holo"


class TestCardDTOWithEditionAndPrintingType:
    """Tests for CardDTO with new edition and printing_type fields"""
    
    def test_card_dto_includes_edition(self):
        """Test that CardDTO can handle edition field"""
        card_data = {
            'name': 'Charizard',
            'card_number': '004/102',
            'rarity': 'Rare',
            'variant': None,
            'condition': 'Near Mint',
            'printing': '1st Edition Holofoil',
            'edition': '1st-edition',
            'printing_type': 'holo',
            'pull_rate': 3.0,
            'prices': {'market': 250.00},
            'source': 'TCGPlayer',
            'currency': 'USD'
        }
        
        dto = CardDTO(**card_data)
        
        assert dto.name == 'Charizard'
        assert dto.edition == '1st-edition'
        assert dto.printing_type == 'holo'
        assert dto.printing == '1st Edition Holofoil'
    
    def test_card_dto_edition_optional(self):
        """Test that edition field is optional in CardDTO"""
        card_data = {
            'name': 'Pikachu',
            'card_number': '025/102',
            'rarity': 'Common',
            'variant': None,
            'condition': 'Near Mint',
            'printing': None,
            'edition': None,  # Optional
            'printing_type': None,  # Optional
            'pull_rate': 1.0,
            'prices': {'market': 0.50},
            'source': 'TCGPlayer',
            'currency': 'USD'
        }
        
        dto = CardDTO(**card_data)
        
        assert dto.name == 'Pikachu'
        assert dto.edition is None
        assert dto.printing_type is None


class TestTCGPlayerParserDroppedOtherBreakdown:
    """dropped_other reason breakdown (code_card vs missing_required) must not change
    what parse_cards accepts -- only add diagnostic visibility into why a row with a
    market price present was still rejected."""

    @pytest.fixture
    def parser(self):
        return TCGPlayerParser({"Common": 1}, set_name="First Partner Collection 2026")

    def test_three_code_card_rows_all_drop_with_code_card_reason(self, parser):
        raw_data = {
            "result": [
                {"productName": "Code Card - First Partner Illustration Collection (Series 1)",
                 "rarity": "Code Card", "condition": "Near Mint", "marketPrice": 0.08,
                 "number": "", "printing": "Normal"},
                {"productName": "Code Card - First Partner Illustration Collection (Series 2)",
                 "rarity": "Code Card", "condition": "Near Mint", "marketPrice": 0.16,
                 "number": "", "printing": "Normal"},
                {"productName": "Code Card - First Partner Illustration Collection (Series 3)",
                 "rarity": "Code Card", "condition": "Near Mint", "marketPrice": 0.07,
                 "number": "", "printing": "Normal"},
            ]
        }

        cards = parser.parse_cards(raw_data)

        assert cards == []
        report = parser.last_card_parse_report
        assert report["raw_rows"] == 3
        assert report["payload_cards"] == 0
        assert report["dropped_other_code_card"] == 3
        assert report["dropped_other_missing_required"] == 0

    def test_mixed_code_card_and_real_card_rows(self, parser):
        raw_data = {
            "result": [
                {"productName": "Code Card - Some Collection", "rarity": "Code Card",
                 "condition": "Near Mint", "marketPrice": 0.08, "number": "", "printing": "Normal"},
                {"productName": "Pikachu - 025/128", "rarity": "Common",
                 "condition": "Near Mint", "marketPrice": 4.99, "number": "025/128",
                 "printing": "Normal"},
            ]
        }

        cards = parser.parse_cards(raw_data)

        assert len(cards) == 1
        report = parser.last_card_parse_report
        assert report["payload_cards"] == 1
        assert report["dropped_other_code_card"] == 1
        assert report["dropped_other_missing_required"] == 0

    def test_missing_required_field_rows_are_counted_separately_from_code_cards(self, parser):
        raw_data = {
            "result": [
                {"productName": None, "rarity": "Common", "condition": "Near Mint",
                 "marketPrice": 4.99, "number": "001/128", "printing": "Normal"},
            ]
        }

        cards = parser.parse_cards(raw_data)

        assert cards == []
        report = parser.last_card_parse_report
        assert report["dropped_other_code_card"] == 0
        assert report["dropped_other_missing_required"] == 1
