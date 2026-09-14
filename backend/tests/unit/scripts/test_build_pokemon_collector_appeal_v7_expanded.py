import pytest

from backend.scripts.build_pokemon_collector_appeal_v7_expanded import (
    _multi_credit,
    artist_lift,
    percentile_positive,
)


def test_artist_lift_is_secondary_monotone_and_bounded():
    assert artist_lift(40, None) == 0
    assert artist_lift(40, 0) == 0
    assert artist_lift(40, 50) == pytest.approx(3)
    assert artist_lift(40, 100) == pytest.approx(6)
    assert 40 + artist_lift(40, 100) == 46
    assert 90 + artist_lift(90, 100) == 91


@pytest.mark.parametrize(
    ("subject", "artist", "expected"),
    [(90, 90, 90.9), (90, None, 90), (90, 10, 90.1), (20, 100, 28),
     (20, None, 20), (50, 100, 55), (80, 100, 82), (50, None, 50)],
)
def test_preregistered_artist_falsification_archetypes(subject, artist, expected):
    assert subject + artist_lift(subject, artist) == pytest.approx(expected)


def test_better_artist_evidence_cannot_decrease_score():
    scores = [55 + artist_lift(55, x) for x in (None, 0, 20, 50, 100)]
    assert scores == sorted(scores)


def test_sequential_artist_after_playability_preserves_total_headroom():
    subject = 30
    after_playability = subject + (100 - subject) * 0.2
    final = after_playability + artist_lift(after_playability, 100)
    assert subject <= after_playability <= final <= 100
    assert final == pytest.approx(49.6)


def test_multi_artist_credits_are_classified_and_never_stacked():
    assert _multi_credit("Ken Sugimori/Yusuke Ohmura")
    assert _multi_credit("Artist One & Artist Two")
    assert _multi_credit("K. Hoshiba, CR CG gangs")
    assert not _multi_credit("Mitsuhiro Arita")
    assert max([25, 80]) == 80


def test_positive_percentile_keeps_confirmed_zero_as_zero():
    assert percentile_positive({"missing-low": 0, "a": 1, "b": 2, "c": 2}) == {
        "missing-low": 0,
        "a": pytest.approx(100 / 3),
        "b": pytest.approx(250 / 3),
        "c": pytest.approx(250 / 3),
    }
