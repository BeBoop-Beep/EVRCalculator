# eBay D3 blind human review runbook

Start or resume the blinded queue:

`python -m backend.scripts.ebay_gold_review_server --partition D3_BLIND_REVIEW --reviewer YOUR_ALIAS`

Show resume-safe summary only:

`python -m backend.scripts.ebay_gold_review_server --partition D3_BLIND_REVIEW --reviewer YOUR_ALIAS --summary`

The queue is append-only. Notes and skips do not count as labels. Images remain visible
so humans can label image-only slabs as `GRADED`. Cohort membership, matcher output,
confidence, evidence, selection rationale, and all price fields remain hidden.
