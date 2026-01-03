import sys
import os

# Add path to import controllers and orchestrators
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.services.orchestrators.tcg_orchestrator import TCGOrchestrator

class IngestService:
    """
    Top-level entry point for ingesting any product type.
    Routes by collection type (TCG, Labubu, etc.) to collection-specific orchestrators.
    
    Routing Hierarchy:
    1. Collection Type (TCG, Labubu, etc.)
    2. Collection-Specific Orchestrator (TCGOrchestrator, LabubuOrchestrator, etc.)
    3. Type-Specific Orchestrator (PokemonTCGOrchestrator, MagicTCGOrchestrator, etc.)
    4. Database Operations (Set → Cards → Prices → Sealed Products)
    """
    
    def __init__(self):
        self.tcg_orchestrator = TCGOrchestrator()
        # Future: self.labubu_orchestrator = LabubuOrchestrator()
    
    def ingest(self, data):
        """
        Route ingestion request by collection type to appropriate orchestrator.
        
        Args:
            data: Dictionary containing product data with a 'collection' field determining the type
            
        Returns:
            Dictionary with ingestion results
        """
        try:
            print("\n[ROUTING] Starting ingestion routing...")
            
            # Determine collection type from data
            collection_data = data.get('collection')
            if not collection_data:
                raise ValueError("Data must contain 'collection' field to determine product type")
            
            # Extract collection name (handle both dict and string)
            if isinstance(collection_data, dict):
                collection_name = collection_data.get('name', '').lower()
            else:
                collection_name = str(collection_data).lower()
            
            # Dynamically route to orchestrator based on collection name
            orchestrator_attr = f"{collection_name}_orchestrator"
            
            if not hasattr(self, orchestrator_attr):
                raise ValueError(
                    f"No orchestrator found for collection type: '{collection_name}'. "
                    f"Expected attribute: '{orchestrator_attr}'"
                )
            
            orchestrator = getattr(self, orchestrator_attr)
            print(f"[PKG] Collection: {collection_name.upper()} - Routing to {collection_name} orchestrator...")
            return orchestrator.ingest(data)
            
        except Exception as e:
            print(f"[ERROR] Ingestion routing error: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }

