import sys
import os

# Add path to import services
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.services.ingest_service import IngestService

class IngestController:
    """Controller for receiving and validating ingestion requests"""
    
    def __init__(self):
        self.ingest_service = IngestService()
    
    def ingest(self, payload):
        """
        Receive payload and delegate to ingestion service
        
        Args:
            payload: Dictionary containing scraped data (set, cards, sealed_products)
            
        Returns:
            Dictionary with ingestion results or None on failure
        """
        # Validate payload at controller level
        if not self._validate_request(payload):
            return {
                'success': False,
                'error': 'Invalid payload structure'
            }
        
        # Delegate to service
        try:
            result = self.ingest_service.process_ingestion(payload)
            return result
        except Exception as e:
            print(f"❌ Controller error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _validate_request(self, payload):
        """Basic validation at controller level"""
        if not isinstance(payload, dict):
            print("❌ Payload must be a dictionary")
            return False
        
        required_keys = ['set', 'cards']
        for key in required_keys:
            if key not in payload:
                print(f"❌ Payload missing required key: {key}")
                return False
        
        return True
