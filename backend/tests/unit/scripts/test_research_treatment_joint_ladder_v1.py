import math
import numpy as np

from backend.scripts.research_treatment_joint_ladder_v1 import fit, treatment_levels


def test_joint_model_recovers_latent_levels_and_shared_scarcity():
    theta_ur = -0.3
    theta_sir = 1.0
    scarcity = 1.5
    artist = 0.8
    specs = [
        ("Ultra Rare", "Double Rare", 0.4, 0.0),
        ("Ultra Rare", "Double Rare", 1.0, 0.0),
        ("Special Illustration Rare", "Double Rare", 1.7, 0.2),
        ("Special Illustration Rare", "Double Rare", 2.2, -0.1),
        ("Special Illustration Rare", "Ultra Rare", 0.5, 0.3),
        ("Special Illustration Rare", "Ultra Rare", 0.9, -0.2),
    ]
    levels = {"Double Rare": 0.0, "Ultra Rare": theta_ur, "Special Illustration Rare": theta_sir}
    rows = []
    for i, (high, low, scarcity_x, artist_x) in enumerate(specs):
        rows.append({
            "cluster_key": f"c{i}",
            "high_treatment": high,
            "low_treatment": low,
            "scarcity_log_ratio": scarcity_x,
            "artist_delta": artist_x * 100.0,
            "mean_log_ratio": levels[high] - levels[low] + scarcity * scarcity_x + artist * artist_x,
        })
    beta, rank, condition = fit(rows)
    assert rank == 4
    assert condition < 50
    assert np.allclose(beta, [theta_ur, theta_sir, scarcity, artist], atol=1e-10)
    recovered = treatment_levels(beta)
    assert math.isclose(recovered["Double Rare"], 0.0)
    assert math.isclose(recovered["Ultra Rare"], theta_ur)
    assert math.isclose(recovered["Special Illustration Rare"], theta_sir)
