import math
from backend.scripts.build_treatment_market_prestige_v3_round3_magnitude import EQUIVALENCE,GATES,PAIR
def test_equivalence_margin_is_preregistered_25_percent():assert EQUIVALENCE==math.log(1.25)
def test_set_support_is_fixed_before_results():assert GATES["minimum_set_ir"]==10 and GATES["minimum_set_sir"]==5
def test_ir_sir_pair_is_explicit_without_forced_order():assert set(PAIR)=={"illustration_rare","special_illustration_rare"}
