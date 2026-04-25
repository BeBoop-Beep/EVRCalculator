from backend.simulations.evrSimulator import _should_use_monte_carlo_v2


class _MegaNoFlag:
    ERA = "Mega Evolution"


class _SVFlagStringFalse:
    ERA = "Scarlet and Violet"
    USE_MONTE_CARLO_V2 = "false"


class _LegacyNoFlag:
    ERA = "Black and White"


class _ExplicitTrue:
    ERA = "Black and White"
    USE_MONTE_CARLO_V2 = True


def test_should_use_monte_carlo_v2_true_for_explicit_flag():
    assert _should_use_monte_carlo_v2(_ExplicitTrue()) is True


def test_should_use_monte_carlo_v2_true_for_mega_and_sv_even_without_true_flag():
    assert _should_use_monte_carlo_v2(_MegaNoFlag()) is True
    assert _should_use_monte_carlo_v2(_SVFlagStringFalse()) is True


def test_should_use_monte_carlo_v2_false_for_legacy_era_without_flag():
    assert _should_use_monte_carlo_v2(_LegacyNoFlag()) is False
