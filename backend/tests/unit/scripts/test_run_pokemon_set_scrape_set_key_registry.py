from backend.scripts.run_pokemon_set_scrape import (
    build_valid_set_key_registry,
    normalize_set_key_filter,
)


def test_build_valid_set_key_registry_contains_required_runtime_keys():
    registry = build_valid_set_key_registry()

    required_runtime_keys = {
        "scarletAndVioletBase",
        "paldeaEvolved",
        "obsidianFlames",
        "scarletAndViolet151",
        "prismaticEvolutions",
        "blackBolt",
        "whiteFlare",
        "megaEvolution",
        "ascendedHeroes",
        "perfectOrder",
        "callOfLegends",
        "heartgoldAndSoulSilver",
    }

    assert required_runtime_keys.issubset(set(registry["valid_keys"]))
    assert registry["registry_source"] == "SET_CONFIG_MAP"


def test_normalize_set_key_filter_accepts_runtime_keys_unchanged():
    registry = build_valid_set_key_registry()

    for runtime_key in [
        "scarletAndVioletBase",
        "paldeaEvolved",
        "obsidianFlames",
        "scarletAndViolet151",
        "prismaticEvolutions",
        "blackBolt",
        "whiteFlare",
        "megaEvolution",
        "ascendedHeroes",
        "perfectOrder",
        "callOfLegends",
        "heartgoldAndSoulSilver",
    ]:
        resolution = normalize_set_key_filter(runtime_key, registry)
        assert resolution["resolved_set_key_filter"] == runtime_key
        assert resolution["normalized_set_key"] == runtime_key


def test_normalize_set_key_filter_resolves_alias_without_lowercasing_runtime_key():
    registry = build_valid_set_key_registry()

    resolution = normalize_set_key_filter("black bolt", registry)

    assert resolution["resolved_set_key_filter"] == "blackBolt"
    assert resolution["normalized_set_key"] == "blackBolt"


def test_normalize_set_key_filter_rejects_invalid_keys_with_diagnostics():
    registry = build_valid_set_key_registry()

    resolution = normalize_set_key_filter("fakeSet123", registry)

    assert resolution["resolved_set_key_filter"] is None
    assert resolution["raw_set_key"] == "fakeSet123"
    assert resolution["normalized_set_key"] == "fakeSet123"
    assert resolution["valid_key_count"] == len(registry["valid_keys"])
    assert resolution["registry_source"] == "SET_CONFIG_MAP"


def test_build_valid_set_key_registry_preserves_era_filter_behavior():
    registry = build_valid_set_key_registry("scarletAndVioletEra")

    assert "scarletAndVioletBase" in registry["valid_keys"]
    assert "callOfLegends" not in registry["valid_keys"]