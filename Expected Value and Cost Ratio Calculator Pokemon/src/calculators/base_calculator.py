# src/calculators/base_calculator.py
from abc import ABC, abstractmethod
from typing import Dict, Any
import pandas as pd

class BaseCalculator(ABC):
    """
    Abstract base class for all calculators.
    Ensures consistent interface and makes it easy to add new calculation types.
    """
    
    def __init__(self, config: Any):
        self.config = config
        self._results = {}
    
    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Perform the calculation and return results.
        
        Args:
            df: Processed dataframe with card data
            
        Returns:
            Dictionary containing calculation results
        """
        pass
    
    @abstractmethod
    def get_result_schema(self) -> Dict[str, str]:
        """
        Return the schema of results this calculator produces.
        
        Returns:
            Dictionary mapping result keys to their descriptions
        """
        pass
    
    def validate_input(self, df: pd.DataFrame) -> bool:
        """
        Validate that the input dataframe has required columns.
        Override in subclasses for specific validation needs.
        """
        required_columns = ['Rarity', 'Price ($)', 'Pull Rate (1/X)']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        return True
    
    @property
    def results(self) -> Dict[str, Any]:
        """Get the last calculated results."""
        return self._results.copy()
    
    def clear_results(self):
        """Clear stored results."""
        self._results = {}