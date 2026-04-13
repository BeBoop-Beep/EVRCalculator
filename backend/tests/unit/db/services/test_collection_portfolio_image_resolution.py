from backend.db.services.collection_portfolio_service import DEFAULT_COLLECTION_IMAGE_PATH, resolve_display_image


def test_resolve_display_image_card_prefers_variant_large_then_small_then_card_fields():
    resolved = resolve_display_image(
        "card",
        variant_large="https://cdn.example/card-variant-large.png",
        variant_small="https://cdn.example/card-variant-small.png",
        card_large="https://cdn.example/card-large.png",
        card_small="https://cdn.example/card-small.png",
    )

    assert resolved == {
        "image_url": "https://cdn.example/card-variant-large.png",
        "image_type": "card",
        "image_source": "card_variant",
        "source_confidence": "high",
    }


def test_resolve_display_image_card_falls_back_to_default():
    resolved = resolve_display_image("card")

    assert resolved == {
        "image_url": DEFAULT_COLLECTION_IMAGE_PATH,
        "image_type": "card",
        "image_source": "fallback",
        "source_confidence": "low",
    }


def test_resolve_display_image_graded_uses_linked_card_assets_with_medium_confidence():
    resolved = resolve_display_image(
        "graded_card",
        variant_large=None,
        variant_small="https://cdn.example/graded-linked-variant-small.png",
        card_large="https://cdn.example/graded-linked-card-large.png",
        card_small="https://cdn.example/graded-linked-card-small.png",
    )

    assert resolved == {
        "image_url": "https://cdn.example/graded-linked-variant-small.png",
        "image_type": "graded_base_card",
        "image_source": "graded_linked_card_variant",
        "source_confidence": "medium",
    }


def test_resolve_display_image_sealed_uses_source_or_fallback():
    resolved_from_source = resolve_display_image(
        "sealed_product",
        sealed_large="https://cdn.example/sealed-large.png",
        sealed_small="https://cdn.example/sealed-small.png",
    )

    assert resolved_from_source == {
        "image_url": "https://cdn.example/sealed-large.png",
        "image_type": "sealed",
        "image_source": "sealed_product",
        "source_confidence": "high",
    }

    resolved_fallback = resolve_display_image("sealed_product")
    assert resolved_fallback == {
        "image_url": DEFAULT_COLLECTION_IMAGE_PATH,
        "image_type": "fallback",
        "image_source": "fallback",
        "source_confidence": "low",
    }
