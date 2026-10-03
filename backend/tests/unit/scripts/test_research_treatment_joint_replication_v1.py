import numpy as np
from backend.scripts.research_treatment_joint_replication_v1 import fit, metrics

def test_frozen_joint_fit_recovers_parameters():
    rows=[]; ur=-0.2; sir=1.1; scarcity=1.5; artist=.6
    levels={"double rare":0.0,"ultra rare":ur,"special illustration rare":sir}
    specs=[("ultra rare","double rare",.4,.1),("special illustration rare","double rare",1.2,-.2),("special illustration rare","ultra rare",.8,.3),("ultra rare","double rare",.9,-.1),("special illustration rare","double rare",1.7,.2),("special illustration rare","ultra rare",.5,-.3)]
    for i,(h,l,s,a) in enumerate(specs):
        rows.append({"cluster_key":f"c{i}","high_treatment":h,"low_treatment":l,"scarcity_log_ratio":s,"artist_delta":a*100,"mean_log_ratio":levels[h]-levels[l]+scarcity*s+artist*a})
    beta,rank,cond=fit(rows)
    assert rank==4 and cond<50
    assert np.allclose(beta,[ur,sir,scarcity,artist],atol=1e-10)
    m=metrics(beta); assert m["sir_vs_double"]>1 and m["sir_vs_ultra"]>1
