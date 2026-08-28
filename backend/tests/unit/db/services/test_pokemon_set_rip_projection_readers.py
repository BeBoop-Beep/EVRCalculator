from types import SimpleNamespace

import pytest

from backend.db.services import pokemon_public_snapshot_service as service
from backend.db.services.pokemon_set_market_service import PokemonSetMarketError


class Query:
    def __init__(self, row, client): self.row, self.client = row, client
    def select(self, columns): self.client.selects.append(columns); return self
    def eq(self, *_args): return self
    def limit(self, *_args): return self
    def execute(self): return SimpleNamespace(data=[self.row] if self.row else [])


class Client:
    def __init__(self, row): self.row, self.selects = row, []
    def table(self, name): assert name == "pokemon_set_page_snapshot_latest"; return Query(self.row, self)


@pytest.mark.parametrize("reader,column,version", [
    (service.get_pokemon_set_rip_bootstrap_snapshot_payload, "rip_bootstrap_json", "pokemon-set-rip-bootstrap-v1"),
    (service.get_pokemon_set_rip_simulation_evidence_snapshot_payload, "rip_simulation_evidence_json", "pokemon-set-rip-simulation-evidence-v1"),
    (service.get_pokemon_set_rip_advanced_snapshot_payload, "rip_advanced_json", "pokemon-set-rip-advanced-v1"),
])
def test_projection_reader_selects_only_split_column_and_uuid_skips_resolver(monkeypatch, reader, column, version):
    client = Client({"set_id": "11111111-1111-1111-1111-111111111111", "updated_at": "now",
                     column: {"contractVersion": version}})
    monkeypatch.setattr(service, "service_read_client", client)
    monkeypatch.setattr(service, "_resolve_set_row", lambda _value: pytest.fail("UUID must skip resolver"))
    payload = reader("11111111-1111-1111-1111-111111111111")
    assert payload["contractVersion"] == version
    assert client.selects == [f"set_id,updated_at,{column}"]
    assert "payload_json" not in client.selects[0]


def test_missing_projection_fails_closed(monkeypatch):
    monkeypatch.setattr(service, "service_read_client", Client({"set_id": "11111111-1111-1111-1111-111111111111"}))
    with pytest.raises(PokemonSetMarketError) as exc:
        service.get_pokemon_set_rip_bootstrap_snapshot_payload("11111111-1111-1111-1111-111111111111")
    assert exc.value.status_code == 503
    assert exc.value.code == "POKEMON_SET_RIP_BOOTSTRAP_SNAPSHOT_INCOMPLETE"

