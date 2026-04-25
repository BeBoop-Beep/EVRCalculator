import pytest

from backend.constants.tcg.pokemon.scarletAndVioletEra.baseConfig import BaseSetConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.blackBolt import SetBlackBoltConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.prismaticEvolutions import SetPrismaticEvolutionsConfig
from backend.constants.tcg.pokemon.scarletAndVioletEra.whiteFlare import SetWhiteFlareConfig


def test_default_chase_metrics_excluded_rarities_is_empty():
    assert BaseSetConfig.CHASE_METRICS_EXCLUDED_RARITIES == frozenset()


@pytest.mark.parametrize(
    "cfg",
    [SetPrismaticEvolutionsConfig, SetBlackBoltConfig, SetWhiteFlareConfig],
)
def test_target_sets_exclude_only_pokeball_from_chase_metrics(cfg):
    exclusions = {str(r).lower().strip() for r in cfg.CHASE_METRICS_EXCLUDED_RARITIES}
    assert "poke ball pattern" in exclusions
    assert "master ball pattern" not in exclusions
