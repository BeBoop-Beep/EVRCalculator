# Bucket 5 performance report

## LIVE DB planning evidence

Collector authority has 18,293 Overall rows. Component cohorts are 15,639
Pokémon, 811 Trainer, 16,775 Artist, and 1,425 Playability. The 207 Collector
facet rows read in about 3.3 ms; colder Overall first-50 is about 25.7 ms; the
old fully enriched page measured about 116.8 ms cold and 1.7 ms warm. Component
RPC measurements are about 101 / 17 / 112 / 21 ms respectively.

Chase contains 4,779 rows. Its first 50 measured about 31.9 ms cold and its
batched image enrichment about 19.2 ms cold. These supplied live measurements
show that the reported 5–10 second experience was not ranking SQL alone.

## FIXTURE BROWSER

Production build, deterministic route interception, fresh browser contexts:

| Scenario | Result |
|---|---:|
| Normal Cards click -> shell | 361.5 ms |
| Normal Cards click -> semantic rows (prewarmed) | 371.1 ms |
| Delayed 250 ms Cards click -> shell | 362.0 ms |
| Delayed 250 ms Cards click -> rows | 787.3 ms |
| Normal component switches P/T/A/Playability | 77.9 / 141.1 / 123.8 / 138.3 ms |
| Delayed component switches P/T/A/Playability | 377.1 / 354.6 / 344.4 / 354.9 ms |
| Overall warm return | 63.2 ms normal / 41.2 ms delayed |
| Premium Chase cold | 401.5 ms |
| Chase -> Collector warm | 72.5 ms; zero Collector row requests |

Default Collector issued exactly one row request and one facet request. Warm
same-query return issued zero row requests. Base issued zero paid Card requests.

Exact fixture JSON sizes: Collector Overall 12,264 B; Pokémon 12,263 B; Artist
13,912 B; Collector facets 184 B; Chase page 23,936 B; Chase facets 184 B.
These are fixture body sizes, not production transfer measurements.

## SOURCE INFERENCE

Overall and non-Artist components remove one score-detail batch; every
Collector lens removes the unused Era batch. Artist retains its single bounded
detail batch. Chase no longer transfers dead prepared/internal columns.
Entitlement checks still precede every service/facet read.

`LIVE_LOCAL_CARD_TIMING_BLOCKED`: authenticated live local routes were not
available, so no production p50/p95 or live-local claims are made.
