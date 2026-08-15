# Stage 1 product-scope validation of Financial RIP V3

- Financial RIP version: `financial_rip_v3_outcome_profile_25_20_15_25_10_5`
- Normalization version: `financial_rip_v3_fixed_absolute_piecewise_v1`
- Composition contract: `sealed-product-composition-stage1-v1`
- Row source: `file`
- Product rows analyzed: **53**

## Question

Financial RIP V3's anchors are absolute and pack-calibrated. This report asks whether the same scale still distinguishes good from bad products WITHIN and ACROSS 1-, 6- and 36-pack opening units, or whether pack count itself has become the dominant signal.

## sleeved_booster_pack (1 pack(s))

- products: **15** across **15** sets (15 scored `ready`)

| statistic | min | p25 | median | p75 | max | mean |
|---|---|---|---|---|---|---|
| **Financial RIP score** | 19.5312 | 28.2303 | 29.9412 | 31.4373 | 38.3953 | 29.1826 |
| product market cost | 6.87 | 9.26 | 10.64 | 11.895 | 16.24 | 10.5947 |

### Raw V3 inputs

| raw input | min | p25 | median | p75 | max | mean |
|---|---|---|---|---|---|---|
| `true_win_probability` | 0.0303 | 0.051 | 0.0601 | 0.071 | 0.0985 | 0.0599 |
| `typical_retention_ratio` | 0.1078 | 0.1416 | 0.1662 | 0.1932 | 0.2089 | 0.166 |
| `average_retention_given_loss` | 0.1511 | 0.1851 | 0.2178 | 0.2455 | 0.2702 | 0.216 |
| `soft_loss_share_given_loss` | 0.0263 | 0.0477 | 0.0573 | 0.0842 | 0.1155 | 0.0653 |
| `p95_threshold_ratio` | 0.5451 | 1.0075 | 1.1907 | 1.4335 | 1.9924 | 1.2179 |
| `realistic_tail_mean_ratio` | 1.1784 | 1.8336 | 2.1084 | 2.4214 | 3.3455 | 2.1106 |
| `p99_threshold_ratio` | 1.822 | 3.2589 | 4.1747 | 5.3736 | 10.2536 | 4.4977 |
| `jackpot_tail_mean_ratio` | 5.4798 | 6.5948 | 10.2304 | 12.1842 | 17.2001 | 10.0501 |
| `base_rtp_excluding_top_1pct` | 0.2007 | 0.2828 | 0.3106 | 0.3289 | 0.4025 | 0.3043 |

### Normalized scores and clipping

| input | norm min | norm p25 | norm median | norm p75 | norm max | norm mean | clipped low % | clipped high % |
|---|---|---|---|---|---|---|---|---|
| `true_win_probability` | 12.1044 | 20.3964 | 24.0524 | 28.3842 | 39.418 | 23.9605 | 0.0 | 0.0 |
| `typical_retention_ratio` | 11.0345 | 15.5497 | 18.8296 | 22.4226 | 24.5136 | 18.7947 | 0.0 | 0.0 |
| `average_retention_given_loss` | 15.1119 | 18.512 | 21.7768 | 24.5505 | 27.0239 | 21.5986 | 0.0 | 0.0 |
| `soft_loss_share_given_loss` | 2.628 | 4.7741 | 5.7292 | 8.4213 | 11.5464 | 6.526 | 0.0 | 0.0 |
| `p95_threshold_ratio` | 21.8039 | 40.2259 | 45.7205 | 53.0052 | 69.7731 | 46.0904 | 0.0 | 0.0 |
| `realistic_tail_mean_ratio` | 31.4246 | 46.6724 | 52.168 | 58.4289 | 72.3036 | 51.6574 | 0.0 | 0.0 |
| `p99_threshold_ratio` | 20.3673 | 33.3206 | 40.6569 | 48.9147 | 72.2436 | 41.487 | 0.0 | 0.0 |
| `jackpot_tail_mean_ratio` | 19.6834 | 23.1865 | 33.5831 | 38.5651 | 49.7422 | 32.4744 | 0.0 | 0.0 |
| `base_rtp_excluding_top_1pct` | 12.5455 | 17.6739 | 19.4103 | 20.559 | 25.3156 | 19.0294 | 0.0 | 0.0 |

### Components

| component | weight | score median | score IQR | contribution median | contribution IQR |
|---|---|---|---|---|---|
| true_win_frequency | 0.25 | 24.0524 | 7.9878 | 6.0131 | 1.997 |
| typical_retention | 0.2 | 18.8296 | 6.873 | 3.7659 | 1.3745 |
| loss_resilience | 0.15 | 16.9625 | 5.0986 | 2.5444 | 0.7648 |
| realistic_upside | 0.25 | 51.8095 | 11.2661 | 12.9524 | 2.8165 |
| jackpot_upside | 0.1 | 34.1764 | 12.8544 | 3.4176 | 1.2854 |
| base_economic_efficiency | 0.05 | 19.4103 | 2.8851 | 0.9705 | 0.1443 |

## booster_bundle (6 pack(s))

- products: **23** across **22** sets (23 scored `ready`)

| statistic | min | p25 | median | p75 | max | mean |
|---|---|---|---|---|---|---|
| **Financial RIP score** | 13.5829 | 22.33 | 27.1449 | 33.3527 | 50.8739 | 28.6098 |
| product market cost | 36.37 | 61.245 | 80.83 | 93.11 | 181.25 | 83.9483 |

### Raw V3 inputs

| raw input | min | p25 | median | p75 | max | mean |
|---|---|---|---|---|---|---|
| `true_win_probability` | 0.0045 | 0.0283 | 0.0495 | 0.0668 | 0.2189 | 0.056 |
| `typical_retention_ratio` | 0.1269 | 0.1646 | 0.2195 | 0.2701 | 0.4672 | 0.2333 |
| `average_retention_given_loss` | 0.1592 | 0.2387 | 0.2749 | 0.3337 | 0.4378 | 0.2822 |
| `soft_loss_share_given_loss` | 0.0209 | 0.0911 | 0.1075 | 0.151 | 0.3323 | 0.1235 |
| `p95_threshold_ratio` | 0.482 | 0.7666 | 0.9956 | 1.3121 | 2.1218 | 1.063 |
| `realistic_tail_mean_ratio` | 0.7378 | 1.3727 | 1.6974 | 1.9729 | 3.8633 | 1.7785 |
| `p99_threshold_ratio` | 0.8801 | 2.3596 | 3.2273 | 4.8673 | 10.8459 | 3.7996 |
| `jackpot_tail_mean_ratio` | 1.0302 | 2.713 | 4.2684 | 6.2482 | 24.6474 | 5.5408 |
| `base_rtp_excluding_top_1pct` | 0.208 | 0.2785 | 0.3382 | 0.3929 | 0.6472 | 0.3513 |

### Normalized scores and clipping

| input | norm min | norm p25 | norm median | norm p75 | norm max | norm mean | clipped low % | clipped high % |
|---|---|---|---|---|---|---|---|---|
| `true_win_probability` | 1.81 | 11.3 | 19.8132 | 26.7154 | 62.5264 | 21.2934 | 0.0 | 0.0 |
| `typical_retention_ratio` | 13.5885 | 18.614 | 25.9341 | 32.6819 | 56.7186 | 27.6749 | 0.0 | 0.0 |
| `average_retention_given_loss` | 15.9153 | 23.8708 | 27.4932 | 33.3657 | 43.7753 | 28.2239 | 0.0 | 0.0 |
| `soft_loss_share_given_loss` | 2.0856 | 9.1126 | 10.7533 | 15.0986 | 33.235 | 12.3452 | 0.0 | 0.0 |
| `p95_threshold_ratio` | 19.28 | 30.6631 | 39.8232 | 49.3641 | 71.2183 | 40.5018 | 0.0 | 0.0 |
| `realistic_tail_mean_ratio` | 19.6739 | 36.6054 | 43.9485 | 49.4576 | 75.7554 | 43.8391 | 0.0 | 0.0 |
| `p99_threshold_ratio` | 10.4179 | 25.5427 | 33.196 | 45.0961 | 74.2243 | 35.2434 | 0.0 | 0.0 |
| `jackpot_tail_mean_ratio` | 4.0369 | 10.2839 | 15.6954 | 22.1143 | 62.6895 | 18.4247 | 0.0 | 0.0 |
| `base_rtp_excluding_top_1pct` | 12.9989 | 17.4051 | 21.1381 | 24.5549 | 55.8979 | 23.5049 | 0.0 | 0.0 |

### Components

| component | weight | score median | score IQR | contribution median | contribution IQR |
|---|---|---|---|---|---|
| true_win_frequency | 0.25 | 19.8132 | 15.4154 | 4.9533 | 3.8538 |
| typical_retention | 0.2 | 25.9341 | 14.0679 | 5.1868 | 2.8136 |
| loss_resilience | 0.15 | 22.481 | 9.0489 | 3.3722 | 1.3574 |
| realistic_upside | 0.25 | 39.486 | 16.3474 | 9.8715 | 4.0868 |
| jackpot_upside | 0.1 | 21.5445 | 14.4558 | 2.1544 | 1.4456 |
| base_economic_efficiency | 0.05 | 21.1381 | 7.1498 | 1.0569 | 0.3575 |

## booster_box (36 pack(s))

- products: **15** across **15** sets (15 scored `ready`)

| statistic | min | p25 | median | p75 | max | mean |
|---|---|---|---|---|---|---|
| **Financial RIP score** | 21.7049 | 27.4589 | 31.6373 | 40.9402 | 51.1428 | 33.9876 |
| product market cost | 168.39 | 288.695 | 306.36 | 365.76 | 460.03 | 312.2407 |

### Raw V3 inputs

| raw input | min | p25 | median | p75 | max | mean |
|---|---|---|---|---|---|---|
| `true_win_probability` | 0.003 | 0.0348 | 0.0457 | 0.0945 | 0.1499 | 0.0606 |
| `typical_retention_ratio` | 0.2584 | 0.3513 | 0.3869 | 0.4734 | 0.6338 | 0.419 |
| `average_retention_given_loss` | 0.2618 | 0.3937 | 0.4205 | 0.4927 | 0.6214 | 0.4435 |
| `soft_loss_share_given_loss` | 0.0075 | 0.1722 | 0.2635 | 0.3966 | 0.7232 | 0.3125 |
| `p95_threshold_ratio` | 0.6887 | 0.9001 | 0.9733 | 1.229 | 2.0533 | 1.1122 |
| `realistic_tail_mean_ratio` | 0.7544 | 1.0328 | 1.2129 | 1.371 | 2.0975 | 1.2523 |
| `p99_threshold_ratio` | 0.8604 | 1.199 | 1.3944 | 1.6025 | 2.1731 | 1.4306 |
| `jackpot_tail_mean_ratio` | 0.9708 | 1.3464 | 1.6335 | 1.8551 | 3.0102 | 1.6908 |
| `base_rtp_excluding_top_1pct` | 0.3635 | 0.4181 | 0.4503 | 0.549 | 0.682 | 0.4902 |

### Normalized scores and clipping

| input | norm min | norm p25 | norm median | norm p75 | norm max | norm mean | clipped low % | clipped high % |
|---|---|---|---|---|---|---|---|---|
| `true_win_probability` | 1.2184 | 13.924 | 18.2728 | 37.0555 | 49.9888 | 23.0037 | 0.0 | 0.0 |
| `typical_retention_ratio` | 31.1253 | 43.5106 | 48.2547 | 57.3363 | 72.5362 | 50.8387 | 0.0 | 0.0 |
| `average_retention_given_loss` | 26.177 | 39.3705 | 42.0548 | 49.2734 | 62.1383 | 44.3457 | 0.0 | 0.0 |
| `soft_loss_share_given_loss` | 0.75 | 17.2162 | 26.3464 | 39.6619 | 72.3222 | 31.253 | 0.0 | 0.0 |
| `p95_threshold_ratio` | 27.548 | 36.005 | 38.9332 | 46.8708 | 70.5331 | 42.5341 | 0.0 | 0.0 |
| `realistic_tail_mean_ratio` | 20.1167 | 27.5423 | 32.3447 | 36.5597 | 51.9495 | 32.9075 | 0.0 | 0.0 |
| `p99_threshold_ratio` | 10.1974 | 13.917 | 15.9951 | 18.1494 | 23.7869 | 16.2747 | 0.0 | 0.0 |
| `jackpot_tail_mean_ratio` | 3.8087 | 5.2431 | 6.325 | 7.1509 | 11.3443 | 6.516 | 0.0 | 0.0 |
| `base_rtp_excluding_top_1pct` | 22.7199 | 27.262 | 31.2895 | 43.6205 | 60.2476 | 36.4706 | 0.0 | 0.0 |

### Components

| component | weight | score median | score IQR | contribution median | contribution IQR |
|---|---|---|---|---|---|
| true_win_frequency | 0.25 | 18.2728 | 23.1315 | 4.5682 | 5.7828 |
| typical_retention | 0.2 | 48.2547 | 13.8257 | 9.6509 | 2.7652 |
| loss_resilience | 0.15 | 37.3423 | 13.5068 | 5.6013 | 2.026 |
| realistic_upside | 0.25 | 34.74 | 8.7806 | 8.685 | 2.1951 |
| jackpot_upside | 0.1 | 9.7096 | 2.7214 | 0.971 | 0.2722 |
| base_economic_efficiency | 0.05 | 31.2895 | 16.3585 | 1.5645 | 0.8179 |

## Cross-family comparison

### Score compression

| family | score median | score IQR | score range |
|---|---|---|---|
| sleeved_booster_pack | 29.9412 | 3.2071 | 18.8641 |
| booster_bundle | 27.1449 | 11.0227 | 37.291 |
| booster_box | 31.6373 | 13.4814 | 29.4379 |

### Raw ratio medians by family (the mechanical concentration check)

| metric | sleeved_booster_pack | booster_bundle | booster_box |
|---|---|---|---|
| baseRtpExcludingTop1PctMedian | 0.3106 | 0.3382 | 0.4503 |
| jackpotTailMeanRatioMedian | 10.2304 | 4.2684 | 1.6335 |
| p95ThresholdRatioMedian | 1.1907 | 0.9956 | 0.9733 |
| p99ThresholdRatioMedian | 4.1747 | 3.2273 | 1.3944 |
| realisticTailMeanRatioMedian | 2.1084 | 1.6974 | 1.2129 |
| trueWinProbabilityMedian | 0.0601 | 0.0495 | 0.0457 |
| typicalRetentionRatioMedian | 0.1662 | 0.2195 | 0.3869 |

### Component separation (within-family score IQR)

A component whose IQR is ~0 inside a family is no longer distinguishing products there.

| component | sleeved_booster_pack | booster_bundle | booster_box |
|---|---|---|---|
| true_win_frequency | 7.9878 | 15.4154 | 23.1315 |
| typical_retention | 6.873 | 14.0679 | 13.8257 |
| loss_resilience | 5.0986 | 9.0489 | 13.5068 |
| realistic_upside | 11.2661 | 16.3474 | 8.7806 |
| jackpot_upside | 12.8544 | 14.4558 | 2.7214 |
| base_economic_efficiency | 2.8851 | 7.1498 | 16.3585 |

### What actually orders products inside each family

- **sleeved_booster_pack**: realistic_upside (33.6%), true_win_frequency (23.82%), typical_retention (16.4%)
- **booster_bundle**: realistic_upside (29.37%), true_win_frequency (27.7%), typical_retention (20.22%)
- **booster_box**: true_win_frequency (41.73%), typical_retention (19.95%), realistic_upside (15.84%)

### Clip pressure (inputs pinned at a transform bound)

- **sleeved_booster_pack**: no clipped inputs
- **booster_bundle**: no clipped inputs
- **booster_box**: no clipped inputs
