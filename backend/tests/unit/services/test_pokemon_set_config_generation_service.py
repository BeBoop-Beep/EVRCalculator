import ast
from pathlib import Path

import pytest

from backend.services.pokemon_set_config_generation_service import (
    ConfigGenerationError, apply_approved_pull_model, generate_one_set_config,
)


METADATA = {
    "id": "me5", "name": "Future Set", "series": "Mega Evolution",
    "releaseDate": "2026/08/01", "printedTotal": 100, "total": 120,
    "ptcgoCode": "FUT", "images": {"symbol": "https://api/symbol", "logo": "https://api/logo"},
}


def _checkout(tmp_path: Path, alias: str = '"existing": "existing",') -> Path:
    era = tmp_path / "backend/constants/tcg/pokemon/megaEvolutionEra"
    era.mkdir(parents=True)
    (era / "baseConfig.py").write_text(
        "from types import MappingProxyType\n"
        "class BaseSetConfig:\n"
        "    RARITY_MAPPING = MappingProxyType({'common': 'common', 'rare': 'rare', 'hit': 'hits'})\n",
        encoding="utf-8",
    )
    (era / "setMap.py").write_text(
        "from .existing import Existing\n\n"
        "SET_CONFIG_MAP = {\n    'existing': Existing,\n}\n\n"
        f"SET_ALIAS_MAP = {{\n    {alias}\n}}\n",
        encoding="utf-8",
    )
    return tmp_path


def test_generation_is_targeted_authoritative_numeric_and_idempotent(tmp_path):
    root = _checkout(tmp_path)
    first = generate_one_set_config(
        root, METADATA, card_details_url="https://tcg/cards", sealed_details_url="https://tcg/sealed",
    )
    config = first.config_path.read_text(encoding="utf-8")
    assert "SYMBOL_IMAGE_URL = 'https://api/symbol'" in config
    assert "LOGO_IMAGE_URL = 'https://api/logo'" in config
    assert 'PULL_MODEL_STATUS = "pending"' in config
    assert "USE_MONTE_CARLO_V2 = False" in config
    assert "'hit': 0.0" in config
    assert '"rarity": ""' not in config
    ast.parse(config)
    map_after = first.set_map_path.read_text(encoding="utf-8")
    assert "from .existing import Existing" in map_after
    assert "'me5': 'futureSet'" in map_after
    assert "'fut': 'futureSet'" in map_after
    second = generate_one_set_config(
        root, METADATA, card_details_url="https://tcg/cards", sealed_details_url="https://tcg/sealed",
    )
    assert second.changed_paths == ()
    assert second.set_map_path.read_text(encoding="utf-8") == map_after


def test_alias_collision_rejects_without_writing_config(tmp_path):
    root = _checkout(tmp_path, alias='"me5": "anotherSet",')
    with pytest.raises(ConfigGenerationError, match="alias collision"):
        generate_one_set_config(
            root, METADATA, card_details_url="https://tcg/cards", sealed_details_url="https://tcg/sealed",
        )
    assert not (root / "backend/constants/tcg/pokemon/megaEvolutionEra/futureSet.py").exists()


def test_specialty_series_does_not_inherit_mega(tmp_path):
    root = _checkout(tmp_path)
    with pytest.raises(ConfigGenerationError, match="unsupported"):
        generate_one_set_config(
            root, {**METADATA, "series": "Anniversary"},
            card_details_url="https://tcg/cards", sealed_details_url="https://tcg/sealed",
        )


def test_approved_pull_model_changes_only_target_config(tmp_path):
    root = _checkout(tmp_path)
    generated = generate_one_set_config(
        root, METADATA, card_details_url="https://tcg/cards", sealed_details_url="https://tcg/sealed",
    )
    map_before = generated.set_map_path.read_text(encoding="utf-8")
    path = apply_approved_pull_model(
        root, "megaEvolutionEra", "futureSet",
        {"rarity_denominators": {"common": 25, "rare": 12, "hit": 100}},
    )
    text = path.read_text(encoding="utf-8")
    assert 'PULL_MODEL_STATUS = "approved"' in text
    assert "USE_MONTE_CARLO_V2 = True" in text
    assert "'hit': 100" in text
    assert generated.set_map_path.read_text(encoding="utf-8") == map_before
