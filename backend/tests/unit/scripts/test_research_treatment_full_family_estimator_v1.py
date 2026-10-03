import numpy as np
from backend.scripts.research_treatment_full_family_estimator_v1 import fit

def test_generic_full_family_fit_recovers_coefficients():
    rows=[]
    for i,(s,a) in enumerate([(0.1,-25.0),(0.7,30.0),(0.25,5.0),(1.1,-5.0),(0.45,45.0),(0.9,-20.0)]):
        rows.append({"treatment":"Double Rare","mean_log_ratio":-0.4+1.2*s+0.35*(a/100),"scarcity_log_ratio":s,"artist_delta":a})
        rows.append({"treatment":"Special Illustration Rare","mean_log_ratio":1.45+1.2*(s+0.07)+0.35*((a+3)/100),"scarcity_log_ratio":s+0.07,"artist_delta":a+3})
    beta,rank,condition=fit(rows,"Double Rare","Special Illustration Rare",True)
    assert rank==4
    assert condition<100
    assert np.allclose(beta,[-0.4,1.45,1.2,0.35],atol=1e-10)
