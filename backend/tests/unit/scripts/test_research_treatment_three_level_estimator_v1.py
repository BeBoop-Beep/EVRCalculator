import numpy as np
from backend.scripts.research_treatment_three_level_estimator_v1 import fit

def test_joint_fit_recovers_treatment_and_controls():
    rows=[]
    for subject in range(8):
        scarcity=0.1+0.1*subject
        artist=-30+10*subject
        rows.append({"treatment":"Double Rare","mean_log_ratio":-0.5+1.1*scarcity+0.4*(artist/100),"scarcity_log_ratio":scarcity,"artist_delta":artist})
        rows.append({"treatment":"Special Illustration Rare","mean_log_ratio":1.4+1.1*(scarcity+0.05)+0.4*((artist+5)/100),"scarcity_log_ratio":scarcity+0.05,"artist_delta":artist+5})
    beta,rank,condition=fit(rows,True)
    assert rank==4
    assert condition<100
    assert np.allclose(beta,[-0.5,1.4,1.1,0.4],atol=1e-10)
