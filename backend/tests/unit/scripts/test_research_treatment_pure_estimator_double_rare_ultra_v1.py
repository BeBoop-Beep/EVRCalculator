import numpy as np

from backend.scripts.research_treatment_pure_estimator_double_rare_ultra_v1 import fit_ols


def test_pure_ols_recovers_known_coefficients():
    rows = []
    for scarcity, artist in [
        (0.1, -30.0),
        (0.3, 10.0),
        (0.6, 40.0),
        (1.0, -10.0),
        (1.3, 25.0),
    ]:
        rows.append(
            {
                "mean_log_ratio": 1.5 + 1.2 * scarcity + 0.8 * (artist / 100.0),
                "scarcity_log_ratio": scarcity,
                "artist_delta": artist,
            }
        )
    beta, rank, condition = fit_ols(rows, pure=True)
    assert rank == 3
    assert condition < 20
    assert np.allclose(beta, [1.5, 1.2, 0.8], atol=1e-10)


def test_package_ols_recovers_known_coefficients():
    rows = []
    for artist in [-40.0, 0.0, 20.0, 55.0]:
        rows.append(
            {
                "mean_log_ratio": 2.0 + 0.7 * (artist / 100.0),
                "scarcity_log_ratio": 0.0,
                "artist_delta": artist,
            }
        )
    beta, rank, _ = fit_ols(rows, pure=False)
    assert rank == 2
    assert np.allclose(beta, [2.0, 0.7], atol=1e-10)
