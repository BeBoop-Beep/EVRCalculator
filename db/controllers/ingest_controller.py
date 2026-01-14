import sys
import os

# Add path to import services
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from db.services.ingest_service import IngestService
from constants.products.product_schemas import TYPE_SCHEMAS

class IngestController:
    """Controller for receiving and validating ingestion requests"""
    
    def __init__(self):
        self.ingest_service = IngestService()
    
    def ingest(self, payload):
        """
        Receive payload and delegate to ingestion service
        
        Args:
            payload: Dictionary containing type and data
            
        Returns:
            Dictionary with ingestion results
        """
        # Validate payload at controller level
        if not self._validate_request(payload):
            return {
                'success': False,
                'error': 'Invalid payload structure'
            }
        
        # Route to service
        try:
            data = payload.get('data', {})
            result = self.ingest_service.ingest(data)
            return result
        except Exception as e:
            print(f"[ERROR] Controller error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _validate_request(self, payload):
        """Basic validation at controller level"""
        product_type = payload.get('type')
        if product_type not in TYPE_SCHEMAS:
            return False
        
        # Validate based on type
        schema = TYPE_SCHEMAS[product_type]
        data = payload.get('data', {})
        # Check required keys in data
        for key in schema['required']:
            if key not in data:
                print(f"[ERROR] Payload 'data' missing required key: {key}")
                return False
        
        # Check optional keys in data (if present)
        for key in schema['optional']:
            if key in data and not isinstance(data[key], list):
                print(f"[ERROR] Payload 'data' key '{key}' must be a list if present")
                return False
        
        return True
