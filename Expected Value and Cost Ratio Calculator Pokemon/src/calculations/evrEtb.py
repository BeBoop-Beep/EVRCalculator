import pandas as pd
from typing import Dict, Any

class ETBCalculator:
    """Calculator for ETB (Elite Trainer Box) expected value and ROI analysis."""
    
    def __init__(self, file_path: str, total_packs_per_etb: int = 9, total_ev: float = 0.0):
        """
        Initialize the calculator with file path and pack configuration.
        
        Args:
            file_path: Path to the Excel file containing Pokemon data
            total_packs_per_etb: Number of packs per ETB (default: 9)
            total_ev: Total expected value per pack
        """
        self.file_path = file_path
        self.total_packs_per_etb = total_packs_per_etb
        self.total_ev = total_ev  # Store the total_ev as instance variable
        self.df = None
        self.calculations = {}
        
    def load_data(self) -> pd.DataFrame:
        """Load and validate the spreadsheet data."""
        try:
            self.df = pd.read_excel(self.file_path, engine='openpyxl')
            self._validate_columns()
            return self.df
        except FileNotFoundError:
            raise FileNotFoundError(f"Excel file not found: {self.file_path}")
        except Exception as e:
            raise Exception(f"Error loading Excel file: {str(e)}")
    
    def _validate_columns(self) -> None:
        """Ensure all required columns exist in the DataFrame."""
        required_columns = [
            "ETB Price",
            "ETB Promo Card Price",
        ]
        
        missing_columns = [col for col in required_columns if col not in self.df.columns]
        if missing_columns:
            raise KeyError(f"Missing required columns: {missing_columns}")
    
    def calculate_etb_metrics(self) -> Dict[str, Any]:
        """
        Calculate ETB expected value, net value, and ROI.
        
        Returns:
            Dictionary containing all calculated metrics and input data
        """
        if self.df is None:
            self.load_data()
        
        # Extract input values
        etb_price = self.df["ETB Price"].iloc[0]
        etb_promo_price = self.df["ETB Promo Card Price"].iloc[0]
        total_ev_per_pack = self.total_ev  # Now this will work
        print("total_ev_per_pack: ", total_ev_per_pack)
        
        # Perform calculations
        expected_profit_in_etb = (total_ev_per_pack * self.total_packs_per_etb) + etb_promo_price
        print("expected_profit_in_etb: ", expected_profit_in_etb)
        etb_net_value = expected_profit_in_etb - etb_price
        etb_roi = expected_profit_in_etb / etb_price if etb_price != 0 else 0
        
        # Store calculations
        self.calculations = {
            # Input data
            'etb_market_price': float(etb_price),
            'etb_promo_price': float(etb_promo_price),
            'total_ev_per_pack': float(total_ev_per_pack),
            'total_packs_per_etb': self.total_packs_per_etb,
            
            # Calculated metrics
            'total_etb_ev': float(expected_profit_in_etb),
            'etb_net_value': float(etb_net_value),
            'etb_roi': float(etb_roi),
            'etb_roi_percentage': float(etb_roi * 100),
            
            # Metadata
            'file_path': self.file_path,
            'calculation_timestamp': pd.Timestamp.now().isoformat()
        }
        
        return self.calculations
    
    def get_summary_dict(self) -> Dict[str, Any]:
        """
        Get a summary dictionary suitable for combining with other calculations.
        
        Returns:
            Dictionary with key metrics for easy integration
        """
        if not self.calculations:
            self.calculate_etb_metrics()
        
        return {
            'etb_calculations': {
                'total_etb_ev': self.calculations['total_etb_ev'],
                'etb_net_value': self.calculations['etb_net_value'],
                'etb_roi': self.calculations['etb_roi'],
                'etb_roi_percentage': self.calculations['etb_roi_percentage']
            },
            'etb_inputs': {
                'etb_market_price': self.calculations['etb_market_price'],
                'etb_promo_price': self.calculations['etb_promo_price'],
                'total_ev_per_pack': self.calculations['total_ev_per_pack'],
                'total_packs_per_etb': self.calculations['total_packs_per_etb']
            }
        }
    
    def print_summary(self) -> None:
        """Print a formatted summary of the calculations."""
        if not self.calculations:
            self.calculate_etb_metrics()
        
        print("\n" + "="*50)
        print("ETB CALCULATION SUMMARY")
        print("="*50)
        print(f"ETB Market Price: ${self.calculations['etb_market_price']:.2f}")
        print(f"ETB Promo Price: ${self.calculations['etb_promo_price']:.2f}")
        print(f"EV Per Pack: ${self.calculations['total_ev_per_pack']:.2f}")
        print(f"Packs Per ETB: {self.calculations['total_packs_per_etb']}")
        print("-"*50)
        print(f"Total ETB EV: ${self.calculations['total_etb_ev']:.2f}")
        print(f"ETB Net Value: ${self.calculations['etb_net_value']:.2f}")
        print(f"ETB ROI: {self.calculations['etb_roi']:.4f} ({self.calculations['etb_roi_percentage']:.2f}%)")
        print("="*50)


# Convenience function for backwards compatibility and quick usage
def calculate_etb_metrics(file_path: str, total_packs_per_etb: int = 9, total_ev: float = 0.0, 
                         print_results: bool = True) -> Dict[str, Any]:
    """
    Quick function to calculate ETB metrics and return results.
    
    Args:
        file_path: Path to Excel file
        total_packs_per_etb: Number of packs per ETB
        total_ev: Total expected value per pack
        print_results: Whether to print summary
    
    Returns:
        Dictionary containing all calculations
    """
    calculator = ETBCalculator(file_path, total_packs_per_etb, total_ev)
    results = calculator.calculate_etb_metrics()
    
    if print_results:
        calculator.print_summary()
    
    return results