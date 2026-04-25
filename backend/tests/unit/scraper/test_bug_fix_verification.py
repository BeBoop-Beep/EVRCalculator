"""
Verification test: Proves the exact bug from the issue is fixed.

This test simulates the exact scenario described in the bug report:
- Raw TCGplayer card row with "1st Edition" printing
- Verify it produces cleaned structured card data with edition="1st-edition"
"""

import pytest
from backend.Scraper.helpers.card_helper import parse_tcgplayer_printing, process_card


class TestBugFixVerification:
    """Verify the exact bug scenario from the issue is fixed"""
    
    def test_bug_scenario_1st_edition_preserved(self):
        """
        BEFORE FIX:
          edition = None (bug!)
        
        AFTER FIX:
          edition = "1st-edition" ✓
        """
        # This is the exact test case from the issue requirements
        raw_printing = "1st Edition"
        
        edition, printing_type = parse_tcgplayer_printing(raw_printing)
        
        # VERIFY FIX: Edition is no longer None
        assert edition == "1st-edition", "BUG FIX VERIFIED: Edition is now parsed!"
        assert printing_type == "non-holo"
    
    def test_bug_scenario_unlimited_preserved(self):
        """
        BEFORE FIX:
          edition = None (bug!)
        
        AFTER FIX:
          edition = "unlimited" ✓
        """
        raw_printing = "Unlimited"
        
        edition, printing_type = parse_tcgplayer_printing(raw_printing)
        
        # VERIFY FIX: Edition is no longer None
        assert edition == "unlimited", "BUG FIX VERIFIED: Unlimited edition is now parsed!"
        assert printing_type == "non-holo"
    
    def test_full_flow_dark_omanyte_example(self):
        """
        Test the exact example from the issue requirements.
        
        Input TCGplayer row:
        {
          "productName": "Dark Omanyte",
          "number": "037/105",
          "printing": "1st Edition",
          "condition": "Moderately Played 1st Edition",
          "rarity": "Uncommon",
          "marketPrice": 4.65
        }
        
        Expected output:
        {
          "name": "Dark Omanyte",
          "card_number": "037/105",
          "condition": "Moderately Played",
          "edition": "1st-edition",
          "printing_type": "non-holo"
        }
        """
        raw_card = {
            "productName": "Dark Omanyte",
            "number": "037/105",
            "printing": "1st Edition",
            "condition": "Moderately Played 1st Edition",
            "rarity": "Uncommon",
            "marketPrice": 4.65
        }
        
        pull_rate_mapping = {"Common": 1, "Uncommon": 2, "Rare": 3}
        
        product_name, card_dict = process_card(raw_card, pull_rate_mapping)
        
        # Verify core fields
        assert product_name == "Dark Omanyte"
        assert card_dict['number'] == "037/105"
        
        # VERIFY THE BUG IS FIXED
        assert card_dict['edition'] == "1st-edition", "✓ Edition is preserved!"
        assert card_dict['printing_type'] == "non-holo", "✓ Printing type is correct!"
        assert card_dict['printing'] == "1st Edition", "✓ Raw printing preserved for reference!"
        
        # Verify condition is cleaned
        assert card_dict['condition'] == "Moderately Played"
        
        print("\n✓ BUG FIX VERIFIED: Dark Omanyte example works perfectly!")
        print(f"  edition={card_dict['edition']}")
        print(f"  printing_type={card_dict['printing_type']}")
    
    def test_distinct_variants_1st_edition_vs_unlimited(self):
        """
        CRITICAL BUG TEST:
        Before fix: "1st Edition" and "Unlimited" collapsed into same variant (edition=None)
        After fix: They are distinct variants (different edition values)
        """
        # Test 1st Edition
        edition_1st, print_type_1st = parse_tcgplayer_printing("1st Edition")
        
        # Test Unlimited
        edition_unlimited, print_type_unlimited = parse_tcgplayer_printing("Unlimited")
        
        # VERIFY: They are now DISTINCT
        assert edition_1st != edition_unlimited, \
            "✓ CRITICAL FIX: 1st Edition and Unlimited are now distinct!"
        assert edition_1st == "1st-edition"
        assert edition_unlimited == "unlimited"
        
        # Both should be non-holo
        assert print_type_1st == "non-holo"
        assert print_type_unlimited == "non-holo"
        
        # They have the same printing_type but different editions
        # This means they will create separate card_variants in the database
        # BEFORE FIX: Both would have edition=None, creating only ONE variant
        # AFTER FIX: They create TWO distinct variants
        
        print("\n✓ CRITICAL BUG FIX VERIFIED:")
        print(f"  '1st Edition' → edition='{edition_1st}', printing_type='{print_type_1st}'")
        print(f"  'Unlimited'   → edition='{edition_unlimited}', printing_type='{print_type_unlimited}'")
        print("  These are now DISTINCT card variants! (Bug fixed!)")
    
    def test_vintage_holo_variants_preserved(self):
        """
        Verify that holofoil variants are also properly parsed with editions.
        """
        # Test cases from the issue
        test_cases = [
            ("1st Edition", "1st-edition", "non-holo"),
            ("Unlimited", "unlimited", "non-holo"),
            ("1st Edition Holofoil", "1st-edition", "holo"),
            ("Unlimited Holofoil", "unlimited", "holo"),
            ("Holofoil", "", "holo"),
            ("Reverse Holofoil", "", "reverse-holo"),
        ]
        
        for raw_printing, expected_edition, expected_type in test_cases:
            edition, printing_type = parse_tcgplayer_printing(raw_printing)
            assert edition == expected_edition, \
                f"Failed for '{raw_printing}': expected edition='{expected_edition}', got '{edition}'"
            assert printing_type == expected_type, \
                f"Failed for '{raw_printing}': expected type='{expected_type}', got '{printing_type}'"
        
        print("\n✓ ALL VINTAGE PRINTING VARIANTS CORRECTLY PARSED")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
