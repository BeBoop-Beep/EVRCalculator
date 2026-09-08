from backend.scripts.research_collector_c3a_components import pranks, spearman

def test_positive_percentiles_preserve_zero_and_ties():
    scores=pranks({'zero_a':0,'zero_b':0,'low':1,'tie_a':2,'tie_b':2})
    assert scores['zero_a'] == scores['zero_b'] == 0
    assert scores['tie_a'] == scores['tie_b']
    assert scores['low'] < scores['tie_a']

def test_rank_stability_is_one_for_identical_order():
    assert spearman({'a':0,'b':1,'c':2},{'a':0,'b':10,'c':20}) == 1
