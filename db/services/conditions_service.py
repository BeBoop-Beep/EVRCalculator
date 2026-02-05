"""
Conditions Service - Handles condition lookups with caching
"""

import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.repositories.conditions_repository import get_condition_by_name


class ConditionsService:
    """Service for condition-related operations with caching"""
    
    _near_mint_id_cache = None
    
    @classmethod
    def get_near_mint_condition_id(cls) -> int:
        """
        Get the condition ID for "Near Mint" condition.
        Caches the result to avoid repeated database lookups.
        
        Returns:
            The condition ID for Near Mint
            
        Raises:
            ValueError: If Near Mint condition not found in database
        """
        if cls._near_mint_id_cache is None:
            condition = get_condition_by_name("Near Mint")
            if not condition:
                raise ValueError("'Near Mint' condition not found in database. Please ensure conditions are seeded.")
            cls._near_mint_id_cache = condition['id']
            print(f"[INFO] Cached Near Mint condition ID: {cls._near_mint_id_cache}")
        
        return cls._near_mint_id_cache
    
    @classmethod
    def get_condition_id_by_name(cls, name: str) -> int:
        """
        Get condition ID by name.
        
        Args:
            name: Condition name (e.g., 'Near Mint', 'Lightly Played')
            
        Returns:
            The condition ID
            
        Raises:
            ValueError: If condition not found
        """
        condition = get_condition_by_name(name)
        if not condition:
            raise ValueError(f"Condition '{name}' not found in database")
        return condition['id']
    
    @classmethod
    def clear_cache(cls):
        """Clear the cached condition ID (useful for testing)"""
        cls._near_mint_id_cache = None
