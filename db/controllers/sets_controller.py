import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.services.sets_service import SetsService

class SetsController:
    """Controller for set operations - routes to service layer"""
    
    def __init__(self):
        self.sets_service = SetsService()
    
    def get_or_create_set(self, set_data):
        """
        Route to service to get or create set
        
        Args:
            set_data: Dictionary with set information (name, abbreviation, tcg, release_date)
            
        Returns:
            str: Set ID (UUID) or None on failure
        """
        return self.sets_service.get_or_create_set(set_data)
