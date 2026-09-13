from backend.scripts.certify_ebay_d3_v3 import coverage_metrics,high_precision_metrics,wilson


def row(card,gold,state):return {"canonical_card_id":card,"target_card_name":card,"human_gold":gold,"matcher_state":state}


def test_precision_uses_all_high_rows_and_ambiguous_is_false_positive():
 rows=[row("a","EXACT_TARGET_MATCH","HIGH_CONFIDENCE"),row("b","AMBIGUOUS","HIGH_CONFIDENCE"),row("c","GRADED","HIGH_CONFIDENCE")]
 found=high_precision_metrics(rows)
 assert found["evaluable_rows"]==3 and found["human_ambiguous_rows"]==1
 assert (found["true_positives"],found["false_positives"],found["precision"])==(1,2,0.33333333)
 assert found["false_positives_by_human_label"]=={"AMBIGUOUS":1,"GRADED":1}


def test_wilson_matches_preregistered_power_case():
 assert wilson(299,300)==[0.98136331,0.99941134]


def test_coverage_uses_fixed_card_denominator_and_medium_does_not_count():
 rows=[]
 for card in range(70):
  rows.extend([row(str(card),"EXACT_TARGET_MATCH","HIGH_CONFIDENCE" if card<56 else "MEDIUM_CONFIDENCE")]+[row(str(card),"GRADED","REJECTED") for _ in range(5)])
 found=coverage_metrics(rows)
 assert found["logical_rows"]==420 and found["all_cards_have_six"] is True
 assert found["covered_cards"]==56 and found["card_coverage"]==.8
 assert found["false_negatives"]==14 and found["medium_count"]==14
