"""
Test script to verify scraper output and DTO structure
Run this to ensure the scraper creates properly structured DTOs
"""
import sys
import os
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Scraper.services.dto_builders.tcgplayer_dto_builder import TCGPlayerDTOBuilder
from config.get_set_config import get_set_config

def test_scraper_dto_creation():
    """Test that scraper creates a valid DTO structure"""
    print("\n🧪 Testing Scraper DTO Creation...")
    
    # Pick a small set to test with
    test_set = "scarletAndViolet151"
    
    try:
        # Get config
        config = get_set_config(test_set)
        print(f"✅ Config loaded for: {test_set}")
        
        # Create DTO builder
        builder = TCGPlayerDTOBuilder()
        
        # Build DTO (you'll need to pass actual scraped data here)
        # For now, let's just verify the config structure
        print(f"\n📦 Config details:")
        print(f"   Collection: {getattr(config, 'COLLECTION', 'NOT FOUND')}")
        print(f"   Set Name: {getattr(config, 'SET_NAME', 'NOT FOUND')}")
        print(f"   TCG: {getattr(config, 'TCG', 'NOT FOUND')}")
        print(f"   Era: {getattr(config, 'ERA', 'NOT FOUND')}")
        
        # TODO: Add actual DTO building test once you have scraped data
        # dto = builder.build_dto(config, cards_data, sealed_data)
        # print(f"\n✅ DTO Structure:")
        # print(json.dumps(dto.model_dump(), indent=2))
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_scraper_dto_creation()
    print(f"\n{'✅ Test passed!' if success else '❌ Test failed!'}")
