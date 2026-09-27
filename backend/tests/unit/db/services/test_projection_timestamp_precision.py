from datetime import datetime,timezone
import pytest
from backend.db.services.price_storage_v2_projection_gate import _parse_ts

@pytest.mark.parametrize('fraction',['1','12','123','1234','13337','123456'])
@pytest.mark.parametrize('offset',['+00:00','Z'])
def test_postgres_variable_fractional_precision(fraction,offset):
    result=_parse_ts('2026-09-26T22:40:37.'+fraction+offset)
    assert result==datetime(2026,9,26,22,40,37,int(fraction.ljust(6,'0')),tzinfo=timezone.utc)

def test_missing_timestamp_stays_missing():
    assert _parse_ts(None) is None
    assert _parse_ts('not-a-time') is None

def test_whole_seconds_unchanged():
    assert _parse_ts('2026-09-26T22:40:37Z')==datetime(2026,9,26,22,40,37,tzinfo=timezone.utc)
