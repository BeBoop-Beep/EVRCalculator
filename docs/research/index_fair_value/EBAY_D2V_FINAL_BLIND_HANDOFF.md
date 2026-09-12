# eBay D2V Final Blind handoff

Status: BLOCKED — DO NOT UNLOCK FINAL BLIND.

The benchmark manifest records 350 Final Blind rows. Their labels were not loaded or
evaluated. Frozen matcher v1 failed Validation with two catastrophic accessory false
positives and 54/70 HIGH card coverage. No final matcher freeze manifest was created.

Required next step: return to Development, create a new matcher version without using
Final Blind evidence, freeze it, and rerun an independent Validation protocol. Only a
passing committed freeze manifest containing matcher_version, matcher_fingerprint, and
frozen_commit may unlock Final Blind evaluation.

Failed frozen input commit: 705b124e7e939d86944ffc0c647b78ef2ae1052b
Query contract retained: ebay_browse_query_d1_unchanged_v1
Alias registry retained: ebay_set_alias_registry_v1
Variant rules retained: ebay_variant_identity_rules_v1
Condition policy retained: ebay_raw_condition_policy_v1
