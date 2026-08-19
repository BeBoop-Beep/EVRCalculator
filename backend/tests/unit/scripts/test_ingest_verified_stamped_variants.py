from backend.scripts.ingest_verified_stamped_variants import _external_identity_payload

def test_stamped_writer_supplies_canonical_external_variant_key():
    payload = _external_identity_payload("623594", {
        "name": "N's Reshiram", "special_type": "journey-together-stamped"})
    assert payload["external_variant_key"] == (
        "edition=|printing_type=holo|special_type=journey-together-stamped")
