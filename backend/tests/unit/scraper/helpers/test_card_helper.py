"""
Tests for card_helper module, focusing on printing parsing and card processing.
"""

import pytest
from backend.Scraper.helpers.card_helper import (
    parse_tcgplayer_printing,
    clean_condition,
    normalize_condition,
)


class TestParseTCGPlayerPrinting:
    """Tests for parse_tcgplayer_printing() function"""
    
    def test_first_edition_non_holo(self):
        """Test parsing '1st Edition' -> ('1st-edition', 'non-holo')"""
        edition, printing_type = parse_tcgplayer_printing("1st Edition")
        assert edition == "1st-edition"
        assert printing_type == "non-holo"
    
    def test_unlimited_non_holo(self):
        """Test parsing 'Unlimited' -> ('unlimited', 'non-holo')"""
        edition, printing_type = parse_tcgplayer_printing("Unlimited")
        assert edition == "unlimited"
        assert printing_type == "non-holo"
    
    def test_first_edition_holofoil(self):
        """Test parsing '1st Edition Holofoil' -> ('1st-edition', 'holo')"""
        edition, printing_type = parse_tcgplayer_printing("1st Edition Holofoil")
        assert edition == "1st-edition"
        assert printing_type == "holo"
    
    def test_unlimited_holofoil(self):
        """Test parsing 'Unlimited Holofoil' -> ('unlimited', 'holo')"""
        edition, printing_type = parse_tcgplayer_printing("Unlimited Holofoil")
        assert edition == "unlimited"
        assert printing_type == "holo"
    
    def test_holofoil_only(self):
        """Test parsing 'Holofoil' (no edition) -> ('', 'holo')"""
        edition, printing_type = parse_tcgplayer_printing("Holofoil")
        assert edition == ""
        assert printing_type == "holo"
    
    def test_reverse_holofoil(self):
        """Test parsing 'Reverse Holofoil' -> ('', 'reverse-holo')"""
        edition, printing_type = parse_tcgplayer_printing("Reverse Holofoil")
        assert edition == ""
        assert printing_type == "reverse-holo"
    
    def test_reverse_holofoil_with_edition(self):
        """Test parsing '1st Edition Reverse Holofoil' -> ('1st-edition', 'reverse-holo')"""
        edition, printing_type = parse_tcgplayer_printing("1st Edition Reverse Holofoil")
        assert edition == "1st-edition"
        assert printing_type == "reverse-holo"
    
    def test_none_input(self):
        """Test parsing None -> ('', 'non-holo')"""
        edition, printing_type = parse_tcgplayer_printing(None)
        assert edition == ""
        assert printing_type == "non-holo"
    
    def test_empty_string_input(self):
        """Test parsing empty string -> ('', 'non-holo')"""
        edition, printing_type = parse_tcgplayer_printing("")
        assert edition == ""
        assert printing_type == "non-holo"
    
    def test_case_insensitive_first_edition(self):
        """Test case insensitivity for '1st edition' (lowercase)"""
        edition, printing_type = parse_tcgplayer_printing("1st edition")
        assert edition == "1st-edition"
        assert printing_type == "non-holo"
    
    def test_case_insensitive_unlimited(self):
        """Test case insensitivity for 'unlimited' (lowercase)"""
        edition, printing_type = parse_tcgplayer_printing("unlimited")
        assert edition == "unlimited"
        assert printing_type == "non-holo"
    
    def test_case_insensitive_holofoil(self):
        """Test case insensitivity for 'holofoil' (lowercase)"""
        edition, printing_type = parse_tcgplayer_printing("1st edition holofoil")
        assert edition == "1st-edition"
        assert printing_type == "holo"
    
    def test_whitespace_handling(self):
        """Test that extra whitespace is handled correctly"""
        edition, printing_type = parse_tcgplayer_printing("  1st Edition  Holofoil  ")
        assert edition == "1st-edition"
        assert printing_type == "holo"
    
    def test_plain_non_holo(self):
        """Test plain/default non-holo printing"""
        edition, printing_type = parse_tcgplayer_printing("Plain")
        assert edition == ""
        assert printing_type == "non-holo"
    
    def test_unknown_printing(self):
        """Test unknown printing string defaults to non-holo"""
        edition, printing_type = parse_tcgplayer_printing("Unknown Format")
        assert edition == ""
        assert printing_type == "non-holo"


class TestCleanCondition:
    """Tests for clean_condition() function"""
    
    def test_removes_1st_edition_from_condition(self):
        """Test that clean_condition removes '1st Edition' suffix"""
        cleaned = clean_condition("Moderately Played 1st Edition")
        assert cleaned == "Moderately Played"
    
    def test_removes_unlimited_from_condition(self):
        """Test that clean_condition removes 'Unlimited' suffix"""
        cleaned = clean_condition("Near Mint Unlimited")
        assert cleaned == "Near Mint"
    
    def test_removes_holofoil_from_condition(self):
        """Test that clean_condition removes 'Holofoil' suffix"""
        cleaned = clean_condition("Lightly Played Holofoil")
        assert cleaned == "Lightly Played"
    
    def test_removes_reverse_holofoil_from_condition(self):
        """Test that clean_condition removes 'Reverse Holofoil' suffix"""
        cleaned = clean_condition("Near Mint Reverse Holofoil")
        assert cleaned == "Near Mint"


class TestNormalizeCondition:
    """Tests for normalize_condition() function"""
    
    def test_normalize_near_mint(self):
        """Test normalization of 'Near Mint' condition"""
        normalized = normalize_condition("Near Mint")
        assert normalized == "Near Mint"
    
    def test_normalize_moderately_played(self):
        """Test normalization of 'Moderately Played' condition"""
        normalized = normalize_condition("Moderately Played")
        assert normalized == "Moderately Played"
    
    def test_normalize_lightly_played(self):
        """Test normalization of 'Lightly Played' condition"""
        normalized = normalize_condition("Lightly Played")
        assert normalized == "Lightly Played"
    
    def test_normalize_heavily_played(self):
        """Test normalization of 'Heavily Played' condition"""
        normalized = normalize_condition("Heavily Played")
        assert normalized == "Heavily Played"
