# __init__.py
from .initializeCalculations import PackEVInitializer
from .evrCalculator import PackEVCalculator 
from .otherCalculations import PackCalculations
from .packCalculationOrchestrator import PackCalculationOrchestrator

def calculate_pack_stats(file_path, config):
    """Convenience function to maintain backward compatibility"""
    orchestrator = PackCalculationOrchestrator(config)
    return orchestrator.calculate_pack_ev(file_path)

# Define what gets imported with "from package import *"
__all__ = [
    'PackEVInitializer',
    'PackEVCalculator', 
    'PackCalculations',
    'PackCalculationOrchestrator',
    'calculate_pack_stats'
]

# Package metadata
__version__ = '1.0.0'