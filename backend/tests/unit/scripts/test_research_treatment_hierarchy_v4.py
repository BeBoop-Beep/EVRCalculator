from backend.scripts.research_treatment_hierarchy_v4 import _subset_context, _group_sample

def test_subset_context_is_set_family_local():
    ctx={
      "a":{"set":"S1","family":"f","identity":"i1"},
      "b":{"set":"S2","family":"f","identity":"i2"},
      "c":{"set":"S1","family":"g","identity":"i3"},
    }
    assert set(_subset_context(ctx,"S1","f"))=={"a"}

def test_group_sample_is_set_family_local():
    rows=[
      {"set":"S1","family":"f","identity":"i1"},
      {"set":"S2","family":"f","identity":"i2"},
      {"set":"S1","family":"g","identity":"i3"},
    ]
    assert [x["identity"] for x in _group_sample(rows,"S1","f")]==["i1"]
