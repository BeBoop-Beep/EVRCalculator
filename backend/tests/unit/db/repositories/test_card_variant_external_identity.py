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
            'source_reference': 'https://www.tcgplayer.com/product/680481'})

def test_existing_same_mapping_is_idempotent(monkeypatch):
    monkeypatch.setattr(repo, 'get_card_variant_external_identity', lambda *_: {
        'id': 'identity', 'card_variant_id': 'variant-a'})
    assert repo.link_card_variant_external_identity('variant-a', {
        'provider': 'TCGPLAYER', 'external_product_id': 680481,
        'source_reference': 'https://www.tcgplayer.com/product/680481'}) == 'identity'
