import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from db.services.orchestrators.pokemon_tcg_orchestrator import PokemonTCGOrchestrator

class TCGOrchestrator:
    """
    Routes TCG product ingestion to game-specific orchestrators.
    Handles the second level of routing: TCG Type → Game-Specific Orchestrator
    
    Flow: Collection (TCG) → TCG Type (Pokemon/Magic/etc.) → Game-Specific Logic
    """
    
    def __init__(self):
        self.pokemon_tcg_orchestrator = PokemonTCGOrchestrator()
        # Future: self.magic_tcg_orchestrator = MagicTCGOrchestrator()
        # Future: self.yugioh_tcg_orchestrator = YuGiOhTCGOrchestrator()
    
    def ingest(self, data):
        """
        Route TCG data to the appropriate game-specific orchestrator.
        
        Args:
            data: Dictionary containing TCG product data with 'set' identifying the specific game
            
        Returns:
            Dictionary with ingestion results
        """
        try:
            print("\n🎴 TCG Orchestrator: Determining game type...")
            
            # Get the TCG type from gameContext data
            gameContext_id = data.get('gameContext')
            if not gameContext_id:
                raise ValueError("TCG data must contain 'gameContext' section to determine game type")
            
            tcg_type = gameContext_id.get('tcg', '').lower()
            
            # Dynamically route to game-specific orchestrator
            orchestrator_attr = f"{tcg_type}_tcg_orchestrator"
            
            if not hasattr(self, orchestrator_attr):
                raise ValueError(
                    f"No orchestrator found for TCG type: '{tcg_type}'. "
                    f"Expected attribute: '{orchestrator_attr}'"
                )
            
            orchestrator = getattr(self, orchestrator_attr)
            print(f"⚡ Routing to {tcg_type.upper()} TCG orchestrator...")
            return orchestrator.ingest(data)
            
        except Exception as e:
            print(f"❌ TCG orchestrator error: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
