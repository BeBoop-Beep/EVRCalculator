"""
Integration test for the full ingestion pipeline
Tests: Scraper -> DTO -> Ingest Controller -> Orchestrators -> Database
NOTE: Uses mocks to avoid actually writing to the database
"""
import sys
import os
import json
from unittest.mock import patch, MagicMock

# Set fake environment variables BEFORE any imports
os.environ['SUPABASE_URL'] = 'https://fake-project.supabase.co'
os.environ['SUPABASE_KEY'] = 'fake-anon-key-for-testing'

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from db.controllers.ingest_controller import IngestController

def create_mock_payload():
    """Create a mock payload that matches the DTO structure"""
    return {
        "type": "tcg",
        "data": {
            "collection": {
                "name": "tcg"
            },
            "gameContext": {
                "set": "Test Set - Integration Test",
                "abbreviation": "TST",
                "tcg": "pokemon",
                "era": "test_era"
            },
            "cards": [
                {
                    "name": "Test Card 1",
                    "card_number": "001",
                    "rarity": "Common",
                    "variant": "Normal",
                    "pull_rate": 0.5,
                    "prices": {
                        "market": 1.99,
                        "low": 0.99
                    }
                }
            ],
            "sealed_products": [
                {
                    "name": "Test Booster Box",
                    "product_type": "Booster Box",
                    "prices": {
                        "market": 120.00,
                        "low": 100.00
                    }
                }
            ],
            "source": "TEST"
        }
    }

def test_ingestion_flow():
    """Test the complete ingestion flow WITHOUT writing to database"""
    print("\n🧪 Testing Full Ingestion Flow (with mocked database)...")
    print("=" * 60)
    
    try:
        # Create mock payload
        payload = create_mock_payload()
        print("\n1️⃣ Mock Payload Created:")
        print(json.dumps(payload, indent=2))
        
        # Mock only the database operations that currently exist
        with patch('db.repositories.sets_repository.get_set_by_name') as mock_get, \
             patch('db.repositories.sets_repository.insert_set') as mock_insert_set, \
             patch('db.repositories.cards_repository.insert_card') as mock_insert_card:
            
            # Configure mocks to simulate database responses
            mock_get.return_value = MagicMock(data=None)  # Set doesn't exist
            mock_insert_set.return_value = [{'id': 'mock-set-id-12345'}]
            mock_insert_card.return_value = 'mock-card-id-1'
            
            print("🔒 Database mocked - no actual writes will occur")
            
            # Initialize controller
            controller = IngestController()
            print("\n2️⃣ Ingest Controller Initialized")
            
            # Attempt ingestion
            print("\n3️⃣ Starting Ingestion...")
            result = controller.ingest(payload)
            
            # Check results
            print("\n4️⃣ Ingestion Result:")
            print(json.dumps(result, indent=2, default=str))
            
            # Verify mocks were called (proves flow worked)
            print("\n5️⃣ Verifying Flow:")
            print(f"   get_set_by_name called: {mock_get.called}")
            print(f"   insert_set called: {mock_insert_set.called}")
            
            if result.get('success'):
                print("\n✅ INGESTION FLOW SUCCESSFUL!")
                print(f"   GameContext ID: {result.get('gameContext_id')}")
                return True
            else:
                print(f"\n❌ INGESTION FAILED: {result.get('error')}")
                return False
            
    except Exception as e:
        print(f"\n❌ Test Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_payload_structure_validation():
    """Test that payload structure matches expected DTO"""
    print("\n🧪 Testing Payload Structure Validation...")
    
    payload = create_mock_payload()
    data = payload.get('data', {})
    
    # Check required fields
    checks = {
        "collection exists": 'collection' in data,
        "gameContext exists": 'gameContext' in data,
        "gameContext.set exists": data.get('gameContext', {}).get('set') is not None,
        "gameContext.tcg exists": data.get('gameContext', {}).get('tcg') is not None,
        "cards is list": isinstance(data.get('cards'), list),
        "sealed_products is list": isinstance(data.get('sealed_products'), list),
    }
    
    print("\nValidation Checks:")
    all_passed = True
    for check_name, passed in checks.items():
        symbol = "✅" if passed else "❌"
        print(f"   {symbol} {check_name}")
        if not passed:
            all_passed = False
    
    return all_passed

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("INGESTION PIPELINE INTEGRATION TEST")
    print("=" * 60)
    
    # Test 1: Payload structure
    structure_valid = test_payload_structure_validation()
    
    # Test 2: Full ingestion flow
    if structure_valid:
        ingestion_success = test_ingestion_flow()
    else:
        print("\n⚠️  Skipping ingestion test due to invalid payload structure")
        ingestion_success = False
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Payload Structure: {'✅ PASS' if structure_valid else '❌ FAIL'}")
    print(f"Ingestion Flow:    {'✅ PASS' if ingestion_success else '❌ FAIL'}")
    print("=" * 60)
