import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.sets_repository import get_set_by_name, insert_set
from db.repositories.eras_repository import get_era_id_by_name
from db.repositories.tcgs_repository import get_tcg_id_by_name
from datetime import datetime

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
            print("[ERROR] Set name is required")
            return None
        
        # Try to get existing set
        try:
            existing_set = get_set_by_name(set_name)
            if existing_set.data:
                print(f"[PKG] Found existing set: {set_name}")
                return existing_set.data['id']
        except Exception as e:
            print(f"[WARN]  Error checking for existing set: {e}")
        
        # Create new set
        print(f"[PKG] Creating new set: {set_name}")
        
        # Look up era_id from era name
        era_name = set_data.get('era')
        era_id = None
        if era_name:
            era_id = get_era_id_by_name(era_name)
        
        # Look up tcg_id from tcg name
        tcg_name = set_data.get('tcg')
        tcg_id = None
        if tcg_name:
            tcg_id = get_tcg_id_by_name(tcg_name)
        
        # Handle release_date formatting
        release_date = set_data.get('release_date')
        if release_date and isinstance(release_date, str):
            try:
                # Try to parse and format as ISO date (YYYY-MM-DD)
                release_date = datetime.fromisoformat(release_date).date().isoformat()
            except:
                release_date = None
        
        new_set = {
            'name': set_name,
            'abbreviation': set_data.get('abbreviation'),
            'release_date': release_date,
            'era_id': era_id,
            'tcg_id': tcg_id,
        }
        
        try:
            result = insert_set(new_set)
            if result and len(result) > 0:
                return result[0]['id']
            else:
                print(f"[ERROR] Failed to create set: {set_name}")
                return None
        except Exception as e:
            print(f"[ERROR] Error creating set: {e}")
            return None
