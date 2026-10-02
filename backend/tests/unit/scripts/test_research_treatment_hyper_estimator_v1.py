import numpy as np
from backend.scripts.research_treatment_hyper_estimator_v1 import fit

def test_hyper_joint_fit_recovers_coefficients():
    rows=[]
    scarcity=[0.15,0.55,0.95,1.25]
    artist=[-20.0,35.0,5.0,60.0]
    for s,a in zip(scarcity,artist):
        rows.append({"treatment":"Hyper Rare","mean_log_ratio":0.6+1.15*s+0.5*(a/100),"scarcity_log_ratio":s,"artist_delta":a})
        rows.append({"treatment":"Special Illustration Rare","mean_log_ratio":1.5+1.15*(s+0.08)+0.5*((a-7)/100),"scarcity_log_ratio":s+0.08,"artist_delta":a-7})
    beta,rank,condition=fit(rows,True)
    assert rank==4
    assert condition<100
    assert np.allclose(beta,[0.6,1.5,1.15,0.5],atol=1e-10)
