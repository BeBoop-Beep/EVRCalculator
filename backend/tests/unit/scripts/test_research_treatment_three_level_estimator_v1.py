import numpy as np

from backend.scripts.research_treatment_three_level_estimator_v1 import fit


def test_joint_fit_recovers_treatment_and_controls():
    rows = []
    scarcity_values = [0.1, 0.7, 0.25, 1.1, 0.45, 0.9, 0.35, 1.3]
    artist_values = [-30.0, 25.0, 5.0, -10.0, 40.0, -20.0, 15.0, 55.0]
    for scarcity, artist in zip(scarcity_values, artist_values):
        rows.append(
            {
                "treatment": "Double Rare",
                "mean_log_ratio": -0.5 + 1.1 * scarcity + 0.4 * (artist / 100.0),
                "scarcity_log_ratio": scarcity,
                "artist_delta": artist,
            }
        )
        rows.append(
            {
                "treatment": "Special Illustration Rare",
                "mean_log_ratio": 1.4
                + 1.1 * (scarcity + 0.05)
                + 0.4 * ((artist + 5.0) / 100.0),
                "scarcity_log_ratio": scarcity + 0.05,
                "artist_delta": artist + 5.0,
            }
        )
    beta, rank, condition = fit(rows, True)
    assert rank == 4
    assert condition < 100
    assert np.allclose(beta, [-0.5, 1.4, 1.1, 0.4], atol=1e-10)
