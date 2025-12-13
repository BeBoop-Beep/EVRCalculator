import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.sets_repository import get_set_by_name, insert_set

class SetsController:
    """Handles set-specific business logic"""
    
    def get_or_create_set(self, set_data):
        """
        Get existing set or create new one
        
        Args:
            set_data: Dictionary with set information (name, abbreviation, tcg)
            
        Returns:
            str: Set ID (UUID) or None on failure
        """
        set_name = set_data.get('name')
        if not set_name:
            print("❌ Set name is required")
            return None
        
        # Try to get existing set
        existing_set = get_set_by_name(set_name)
        if existing_set:
            print(f"📦 Found existing set: {set_name}")
            return existing_set['id']
        
        # Create new set
        print(f"📦 Creating new set: {set_name}")
        new_set = {
            'name': set_name,
            'abbreviation': set_data.get('abbreviation'),
            'tcg': set_data.get('tcg'),
            'release_date': set_data.get('release_date'),
        }
        
        result = insert_set(new_set)
        if result and len(result) > 0:
            return result[0]['id']
        
        print(f"❌ Failed to create set: {set_name}")
        return None
