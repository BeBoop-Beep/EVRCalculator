import pytest
from backend.db.repositories import card_variant_repository as repo

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
    monkeypatch.setattr(repo, 'supabase', type('S', (), {'table': lambda *_: Query()})())
    with pytest.raises(repo.AmbiguousExternalVariantIdentity):
        repo.get_card_variant_external_identity('tcgplayer', '1')
