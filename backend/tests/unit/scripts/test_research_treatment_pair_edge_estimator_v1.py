import numpy as np
from backend.scripts.research_treatment_pair_edge_estimator_v1 import fit

def test_pair_edge_fit_recovers_coefficients():
    rows=[]
    for s,a in [(0.1,-30.0),(0.5,15.0),(0.9,45.0),(1.2,-10.0),(0.3,60.0)]:
        rows.append({"mean_log_ratio":0.8+1.1*s+0.4*(a/100),"scarcity_log_ratio":s,"artist_delta":a})
    beta,rank,condition=fit(rows)
    assert rank==3
    assert condition<100
    assert np.allclose(beta,[0.8,1.1,0.4],atol=1e-10)
