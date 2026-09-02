import json, pandas as pd
D = r"d:\EVRCalculator\backend\research\scratch_pass1a"
sp = json.load(open(D+r"\sealed_product_results_all.json"))
df = pd.DataFrame(sp)
print(df.columns.tolist())
loose = df[df.product_family=="loose_booster_pack"]
print(loose[["pack_count","random_pack_count","collector_appeal_score","overall_rip_v10_score","overall_rip_v10_status" if "overall_rip_v10_status" in df.columns else "product_family"]].describe(include='all'))
print("collector_appeal non-null total:", df.collector_appeal_score.notna().sum(), "/", len(df))
print("overall_rip_v10 non-null total:", df.overall_rip_v10_score.notna().sum(), "/", len(df))
print("by family collector_appeal non-null:")
print(df.groupby("product_family").collector_appeal_score.apply(lambda s: s.notna().sum()))
print("by family overall_rip_v10 non-null:")
print(df.groupby("product_family").overall_rip_v10_score.apply(lambda s: s.notna().sum()))
print("pack_count sample:", loose.pack_count.unique()[:10])
