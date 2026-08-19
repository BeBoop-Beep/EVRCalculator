import pytest
from backend.db.repositories import card_variant_repository as repo
from backend.db.services import supabase_persistence_retry as retry

class Result:
    def __init__(self, data): self.data = data

def test_rejects_attempt_to_move_existing_product(monkeypatch):
    monkeypatch.setattr(repo, 'get_card_variant_external_identity', lambda *_: {
        'id': 'identity', 'card_variant_id': 'variant-a'})
    with pytest.raises(repo.ExternalVariantIdentityConflict):
        repo.link_card_variant_external_identity('variant-b', {
            'provider': 'tcgplayer', 'external_product_id': '680481',
            'external_variant_key': 'edition=|printing_type=holo|special_type=',
            'source_reference': 'https://www.tcgplayer.com/product/680481'})

def test_existing_same_mapping_is_idempotent(monkeypatch):
    monkeypatch.setattr(repo, 'get_card_variant_external_identity', lambda *_: {
        'id': 'identity', 'card_variant_id': 'variant-a'})
    assert repo.link_card_variant_external_identity('variant-a', {
        'provider': 'TCGPLAYER', 'external_product_id': 680481,
        'external_variant_key': 'edition=|printing_type=holo|special_type=',
        'source_reference': 'https://www.tcgplayer.com/product/680481'}) == 'identity'

def test_ambiguous_legacy_lookup_fails_closed(monkeypatch):
    class Query:
        data = None
        def select(self, *_): return self
        def eq(self, *_): return self
        def limit(self, *_): return self
        def execute(self): return type('R', (), {'data': [{'id': 'a'}, {'id': 'b'}]})()
    monkeypatch.setattr(
        repo, 'run_supabase_with_transient_retry',
        lambda operation, **_: operation(type('S', (), {'table': lambda *_: Query()})(), 1))
    with pytest.raises(repo.AmbiguousExternalVariantIdentity):
        repo.get_card_variant_external_identity('tcgplayer', '1')


def test_known_absent_committed_but_lost_insert_reconciles_without_duplicate(monkeypatch):
    rows, inserts, clients = [], [], []
    class Query:
        def __init__(self): self.mode = 'select'; self.payload = None; self.filters = []
        def select(self, *_): return self
        def eq(self, column, value): self.filters.append((column, value)); return self
        def limit(self, *_): return self
        def insert(self, payload): self.mode = 'insert'; self.payload = dict(payload); return self
        def execute(self):
            if self.mode == 'select':
                return Result([row for row in rows if all(str(row.get(k)) == str(v) for k, v in self.filters)])
            inserts.append(self.payload)
            committed = {**self.payload, 'id': 'identity'}
            rows.append(committed)
            if len(inserts) == 1:
                raise ConnectionError('Server disconnected')
            return Result([committed])
    class Client:
        def table(self, *_): return Query()
    def create_client(*_): clients.append(1); return Client()
    monkeypatch.setattr(retry, 'create_client', create_client)
    monkeypatch.setattr(retry.time, 'sleep', lambda *_: None)
    monkeypatch.setattr(retry.random, 'uniform', lambda *_: 0.0)
    identity = {'provider': 'tcgplayer', 'external_product_id': '1',
                'external_variant_key': 'k'}
    assert repo.link_card_variant_external_identity('variant-a', identity, known_absent=True) == 'identity'
    assert len(rows) == len(inserts) == 1
    assert len(clients) >= 3  # insert attempt, retry client, reconciliation read client


def test_known_absent_concurrent_conflicting_mapping_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(repo, 'get_card_variant_external_identity', lambda *_: {
        'id': 'identity', 'card_variant_id': 'variant-other'})
    class Insert:
        def execute(self):
            from postgrest.exceptions import APIError
            raise APIError({'message': 'duplicate', 'code': '23505', 'hint': None, 'details': None})
    class Client:
        def table(self, *_): calls.append(1); return self
        def insert(self, *_): return Insert()
    monkeypatch.setattr(repo, 'run_supabase_with_transient_retry',
                        lambda operation, **_: operation(Client(), 1))
    with pytest.raises(repo.ExternalVariantIdentityConflict):
        repo.link_card_variant_external_identity('variant-a', {
            'provider': 'tcgplayer', 'external_product_id': '1',
            'external_variant_key': 'k'}, known_absent=True)
    assert len(calls) == 1
