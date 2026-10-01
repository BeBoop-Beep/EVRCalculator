# Cards cold path

## Before

`RankingsLazyClient -> dynamic CardRankingsHub -> dynamic active child -> child effects -> facets + rows`

The footer interpreted missing payload as zero, and default data could not begin
until both module boundaries mounted.

## After

`auth resolved -> idle [complete Cards chunk + Collector facets + Overall page 1]`

`Cards intent -> complete Cards chunk preload`

`Cards click -> hub shell -> active Collector reads completed/in-flight cache -> semantic rows`

Collector facets and rows start in parallel. The mounted component uses the
same canonical keys, so it reuses a completed value or joins the in-flight
Promise. Only the active Card lens mounts. Chase data waits for Premium toggle
intent and cannot compete with the default Collector prewarm.

Rows become semantically ready from text, ranks, scores, and controls; Next
Image decoding is not awaited and no full-size image preload was added.
