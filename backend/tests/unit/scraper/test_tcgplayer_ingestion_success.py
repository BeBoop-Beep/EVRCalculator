import pytest
from backend.Scraper.services.orchestrators.tcg_player_orchestrator import validate_ingestion_result

PAYLOAD = {'data': {'cards': [{'prices': {'market': 1.25}}]}}

def _result(**cards):
    return {'success': True, 'set_id': 'set-1', 'details': {'cards': {
        'errors': cards.get('errors', []), 'price_rows_updated': cards.get('updated', 0),
        'ingestion_efficiency': {'attempted_rows': cards.get('attempted', 1),
            'inserted_rows': cards.get('inserted', 1), 'skipped_duplicates': 0}}}}

def test_persisted_priced_payload_succeeds():
    assert validate_ingestion_result(PAYLOAD, _result())['ingestionSuccess'] is True

def test_result_success_false_fails():
    with pytest.raises(RuntimeError): validate_ingestion_result(PAYLOAD, {'success': False})

def test_fatal_card_errors_fail():
    with pytest.raises(RuntimeError): validate_ingestion_result(PAYLOAD, _result(errors=['bad']))

def test_zero_attempted_card_price_writes_fail():
    with pytest.raises(RuntimeError): validate_ingestion_result(PAYLOAD, _result(attempted=0, inserted=0))
