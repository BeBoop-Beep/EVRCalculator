import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.sets_repository import get_set_by_name, insert_set

class SetsService:
    """Service layer for set business logic"""
    
    def get_or_create_set(self, set_data):
        """
        Get existing set or create new one
        
        Args:
            set_data: Dictionary with set information (set, abbreviation, tcg, release_date)
            
        Returns:
            str: Set ID (UUID) or None on failure
        """
        set_name = set_data.get('set')
        if not set_name:
            print("❌ Set name is required")
            return None
        
        # Try to get existing set
        try:
            existing_set = get_set_by_name(set_name)
            if existing_set.data:
                print(f"📦 Found existing set: {set_name}")
                return existing_set.data['id']
        except Exception as e:
            print(f"⚠️  Error checking for existing set: {e}")
        
        # Create new set
        print(f"📦 Creating new set: {set_name}")
        new_set = {
            'name': set_name,
            'abbreviation': set_data.get('abbreviation'),
            'tcg': set_data.get('tcg'),
            'release_date': set_data.get('release_date'),
        }
        
        try:
            result = insert_set(new_set)
            if result and len(result) > 0:
                return result[0]['id']
            else:
                print(f"❌ Failed to create set: {set_name}")
                return None
        except Exception as e:
            print(f"❌ Error creating set: {e}")
            return None
