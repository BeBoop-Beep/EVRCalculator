# Set RIP Consensus Research

READ-ONLY RESEARCH. No Set RIP score is published.

# CURRENT COVERAGE

| Family | Rankable SKUs | Represented sets |
|---|---:|---:|
| Booster Box | 15 | 15 |
| Booster Bundle | 23 | 22 |
| Elite Trainer Box | 27 | 22 |
| Enhanced Booster Box | 2 | 2 |
| Half Booster Box | 7 | 7 |
| Loose Booster Pack | 22 | 22 |
| Pokémon Center Elite Trainer Box | 26 | 22 |
| Sleeved Booster Pack | 15 | 15 |

# LEADING TWO-LEVEL CONSTRUCT

Set RIP should measure a set's average relative ripping quality across eligible sealed-product families. Within each family, all rankable SKU standings are averaged; available eligible family means are then averaged with one equal vote per family.

Leading research candidate: mean SKU standing within each canonical product family, then an unshrunk equal-family arithmetic mean. A set needs at least two eligible families; a family needs at least three represented sets. Missing families are omitted, never zero, and SKU-rich families receive no extra weight.

# SET × FAMILY MATRIX

The JSON contains 272 explicit cells. Missing families are omitted, never zero.

# MULTI-SKU DIAGNOSTICS

10 cells have multiple rankable SKUs. The leading construct uses the mean.

| Set | Family | SKUs (rank: standing) | Best | Median | Mean |
|---|---|---|---:|---:|---:|
| Mega Evolution | elite_trainer_box | Mega Evolution Elite Trainer Box [Mega Gardevoir] (9: 0.692308); Mega Evolution Elite Trainer Box [Mega Lucario] (11: 0.615385) | 0.692308 | 0.653846 | 0.653846 |
| Mega Evolution | pokemon_center_elite_trainer_box | Mega Evolution Pokemon Center Elite Trainer Box (Exclusive) [Mega Gardevoir] (2: 0.96); Mega Evolution Pokemon Center Elite Trainer Box (Exclusive) [Mega Lucario] (7: 0.76) | 0.96 | 0.86 | 0.86 |
| Paradox Rift | elite_trainer_box | Paradox Rift Elite Trainer Box [Roaring Moon] (19: 0.307692); Paradox Rift Elite Trainer Box [Iron Valiant] (21: 0.230769) | 0.307692 | 0.269231 | 0.269231 |
| Paradox Rift | pokemon_center_elite_trainer_box | Paradox Rift Pokemon Center Elite Trainer Box (Exclusive) [Iron Valiant] (13: 0.52); Paradox Rift Pokemon Center Elite Trainer Box (Exclusive) [Roaring Moon] (14: 0.48) | 0.52 | 0.5 | 0.5 |
| Prismatic Evolutions | elite_trainer_box | Prismatic Evolutions Elite Trainer Box (2: 0.961538); Prismatic Evolutions Elite Trainer Box (Dollar General Exclusive) (4: 0.884615) | 0.961538 | 0.923077 | 0.923077 |
| Scarlet and Violet Base Set | elite_trainer_box | Scarlet & Violet Elite Trainer Box [Koraidon] (24: 0.115385); Scarlet & Violet Elite Trainer Box [Miraidon] (27: 0.0) | 0.115385 | 0.057692 | 0.057692 |
| Scarlet and Violet Base Set | pokemon_center_elite_trainer_box | Scarlet & Violet Pokemon Center Elite Trainer Box (Exclusive) [Miraidon] (25: 0.04); Scarlet & Violet Pokemon Center Elite Trainer Box (Exclusive) [Koraidon] (26: 0.0) | 0.04 | 0.02 | 0.02 |
| Surging Sparks | booster_bundle | Surging Sparks Booster Bundle (Retail) (16: 0.318182); Surging Sparks Booster Bundle (LGS) (18: 0.227273) | 0.318182 | 0.272727 | 0.272727 |
| Temporal Forces | elite_trainer_box | Temporal Forces Elite Trainer Box [Iron Leaves ex] (12: 0.576923); Temporal Forces Elite Trainer Box [Walking Wake] (13: 0.538462) | 0.576923 | 0.557692 | 0.557692 |
| Temporal Forces | pokemon_center_elite_trainer_box | Temporal Forces Pokemon Center Elite Trainer Box (Exclusive) [Iron Leaves] (9: 0.68); Temporal Forces Pokemon Center Elite Trainer Box (Exclusive) [Walking Wake] (12: 0.56) | 0.68 | 0.62 | 0.62 |

# FAMILY CORRELATIONS

| Family A | Family B | Overlap N | Spearman |
|---|---|---:|---:|
| booster_box | booster_bundle | 15 | 0.475 |
| booster_box | elite_trainer_box | 15 | 0.649375 |
| booster_box | enhanced_booster_box | 2 | 1.0 |
| booster_box | half_booster_box | 7 | 0.75 |
| booster_box | loose_booster_pack | 15 | 0.246429 |
| booster_box | pokemon_center_elite_trainer_box | 15 | 0.571429 |
| booster_box | sleeved_booster_pack | 15 | 0.246429 |
| booster_bundle | elite_trainer_box | 22 | 0.687394 |
| booster_bundle | enhanced_booster_box | 2 | -1.0 |
| booster_bundle | half_booster_box | 7 | -0.714286 |
| booster_bundle | loose_booster_pack | 22 | 0.338323 |
| booster_bundle | pokemon_center_elite_trainer_box | 22 | 0.590229 |
| booster_bundle | sleeved_booster_pack | 15 | -0.028571 |
| elite_trainer_box | enhanced_booster_box | 2 | 1.0 |
| elite_trainer_box | half_booster_box | 7 | 0.036037 |
| elite_trainer_box | loose_booster_pack | 22 | 0.241876 |
| elite_trainer_box | pokemon_center_elite_trainer_box | 22 | 0.615428 |
| elite_trainer_box | sleeved_booster_pack | 15 | 0.073345 |
| enhanced_booster_box | half_booster_box | 1 | None |
| enhanced_booster_box | loose_booster_pack | 2 | -1.0 |
| enhanced_booster_box | pokemon_center_elite_trainer_box | 2 | 1.0 |
| enhanced_booster_box | sleeved_booster_pack | 2 | 1.0 |
| half_booster_box | loose_booster_pack | 7 | 0.214286 |
| half_booster_box | pokemon_center_elite_trainer_box | 7 | 0.107143 |
| half_booster_box | sleeved_booster_pack | 7 | 0.571429 |
| loose_booster_pack | pokemon_center_elite_trainer_box | 22 | 0.239977 |
| loose_booster_pack | sleeved_booster_pack | 15 | 0.446429 |
| pokemon_center_elite_trainer_box | sleeved_booster_pack | 15 | 0.207143 |

# LEADING RESEARCH ORDERING

| Rank | Set | Set RIP unit | Score ×100 | Families | SKU evidence |
|---:|---|---:|---:|---:|---:|
| 1 | Pitch Black | 0.960123 | 96.012317 | 6 | 6 |
| 2 | Ascended Heroes | 0.867208 | 86.720775 | 4 | 4 |
| 3 | Perfect Order | 0.753677 | 75.367733 | 6 | 6 |
| 4 | Temporal Forces | 0.750493 | 75.049286 | 7 | 9 |
| 5 | Shrouded Fable | 0.740586 | 74.0586 | 4 | 4 |
| 6 | Prismatic Evolutions | 0.650488 | 65.048775 | 4 | 5 |
| 7 | Chaos Rising | 0.645723 | 64.572317 | 6 | 6 |
| 8 | Twilight Masquerade | 0.580833 | 58.083343 | 7 | 7 |
| 9 | Mega Evolution | 0.525478 | 52.547829 | 7 | 9 |
| 10 | Paradox Rift | 0.520341 | 52.034083 | 6 | 8 |
| 11 | Journey Together | 0.464857 | 46.48575 | 6 | 6 |
| 12 | Paldea Evolved | 0.457879 | 45.787929 | 7 | 7 |
| 13 | Stellar Crown | 0.457377 | 45.7377 | 7 | 7 |
| 14 | Scarlet and Violet 151 | 0.445335 | 44.533475 | 4 | 4 |
| 15 | Black Bolt | 0.391969 | 39.19695 | 4 | 4 |
| 16 | White Flare | 0.385622 | 38.56225 | 4 | 4 |
| 17 | Destined Rivals | 0.376326 | 37.632557 | 7 | 7 |
| 18 | Surging Sparks | 0.297391 | 29.739114 | 7 | 8 |
| 19 | Phantasmal Flames | 0.26139 | 26.138967 | 6 | 6 |
| 20 | Scarlet and Violet Base Set | 0.239139 | 23.913917 | 6 | 8 |
| 21 | Obsidian Flames | 0.196294 | 19.629383 | 6 | 6 |
| 22 | Paldean Fates | 0.117797 | 11.779725 | 4 | 4 |

# PREVIOUS VS CURRENT LEADING CONSTRUCT

Old BEST-SKU + prior-strength-2 versus new mean-SKU + no-shrinkage: overlap N=22, Spearman=0.997741, top-five overlap=5, mean absolute movement=0.181818, maximum movement=1.

| Set | Old rank | New rank | Movement | Old unit | New unit |
|---|---:|---:|---:|---:|---:|
| Chaos Rising | 6 | 7 | -1 | 0.609292 | 0.645723 |
| Perfect Order | 4 | 3 | 1 | 0.690258 | 0.753677 |
| Prismatic Evolutions | 7 | 6 | 1 | 0.606735 | 0.650488 |
| Temporal Forces | 3 | 4 | -1 | 0.703631 | 0.750493 |
| Phantasmal Flames | 19 | 19 | 0 | 0.321042 | 0.26139 |
| Journey Together | 11 | 11 | 0 | 0.473643 | 0.464857 |
| Paldea Evolved | 12 | 12 | 0 | 0.467239 | 0.457879 |
| Shrouded Fable | 5 | 5 | 0 | 0.660391 | 0.740586 |
| Scarlet and Violet Base Set | 20 | 20 | 0 | 0.314066 | 0.239139 |
| Black Bolt | 15 | 15 | 0 | 0.42798 | 0.391969 |

# FAMILY-COUNT FAIRNESS

Coverage is a rankability gate only. Every eligible family contributes one vote, regardless of its SKU count. In the current cohort, higher family coverage is negatively rather than positively associated with Set RIP, so this diagnostic does not show a systematic more-families advantage.

Available sets=22; Spearman coverage versus Set RIP=-0.008981; coverage versus better rank=-0.008981.

| Family count | Sets | Average Set RIP unit |
|---:|---:|---:|
| 4 | 7 | 0.514144 |
| 6 | 8 | 0.505193 |
| 7 | 7 | 0.492254 |

# ADDITIONAL-FAMILY IMPACT

Positive delta means the family improves the set's full mean; negative delta means it lowers it.

| Set | Omitted family | Full unit | Without family | Delta |
|---|---|---:|---:|---:|
| Phantasmal Flames | booster_box | 0.26139 | 0.17081 | 0.090579 |
| Phantasmal Flames | booster_bundle | 0.26139 | 0.277304 | -0.015914 |
| Phantasmal Flames | elite_trainer_box | 0.26139 | 0.236745 | 0.024645 |
| Phantasmal Flames | loose_booster_pack | 0.26139 | 0.304144 | -0.042754 |
| Phantasmal Flames | pokemon_center_elite_trainer_box | 0.26139 | 0.265668 | -0.004278 |
| Phantasmal Flames | sleeved_booster_pack | 0.26139 | 0.313668 | -0.052278 |
| Journey Together | booster_box | 0.464857 | 0.543543 | -0.078686 |
| Journey Together | booster_bundle | 0.464857 | 0.421465 | 0.043392 |
| Journey Together | elite_trainer_box | 0.464857 | 0.503983 | -0.039125 |
| Journey Together | loose_booster_pack | 0.464857 | 0.367353 | 0.097505 |
| Journey Together | pokemon_center_elite_trainer_box | 0.464857 | 0.437829 | 0.027029 |
| Journey Together | sleeved_booster_pack | 0.464857 | 0.514972 | -0.050114 |
| Paldea Evolved | booster_box | 0.457879 | 0.42705 | 0.03083 |
| Paldea Evolved | booster_bundle | 0.457879 | 0.511465 | -0.053586 |
| Paldea Evolved | elite_trainer_box | 0.457879 | 0.46368 | -0.0058 |
| Paldea Evolved | half_booster_box | 0.457879 | 0.395304 | 0.062576 |
| Paldea Evolved | loose_booster_pack | 0.457879 | 0.49451 | -0.036631 |
| Paldea Evolved | pokemon_center_elite_trainer_box | 0.457879 | 0.474193 | -0.016313 |
| Paldea Evolved | sleeved_booster_pack | 0.457879 | 0.438954 | 0.018925 |
| Shrouded Fable | booster_bundle | 0.740586 | 0.654115 | 0.086471 |
| Shrouded Fable | elite_trainer_box | 0.740586 | 0.705397 | 0.035189 |
| Shrouded Fable | loose_booster_pack | 0.740586 | 0.828718 | -0.088132 |
| Shrouded Fable | pokemon_center_elite_trainer_box | 0.740586 | 0.774115 | -0.033529 |
| Scarlet and Violet Base Set | booster_box | 0.239139 | 0.258396 | -0.019256 |
| Scarlet and Violet Base Set | booster_bundle | 0.239139 | 0.286967 | -0.047828 |
| Scarlet and Violet Base Set | elite_trainer_box | 0.239139 | 0.275429 | -0.036289 |
| Scarlet and Violet Base Set | loose_booster_pack | 0.239139 | 0.172681 | 0.066458 |
| Scarlet and Violet Base Set | pokemon_center_elite_trainer_box | 0.239139 | 0.282967 | -0.043828 |
| Scarlet and Violet Base Set | sleeved_booster_pack | 0.239139 | 0.158396 | 0.080744 |
| Black Bolt | booster_bundle | 0.391969 | 0.371111 | 0.020859 |
| Black Bolt | elite_trainer_box | 0.391969 | 0.355959 | 0.03601 |
| Black Bolt | loose_booster_pack | 0.391969 | 0.411515 | -0.019546 |
| Black Bolt | pokemon_center_elite_trainer_box | 0.391969 | 0.429293 | -0.037323 |
| Pitch Black | booster_box | 0.960123 | 0.952148 | 0.007975 |
| Pitch Black | booster_bundle | 0.960123 | 0.97033 | -0.010206 |
| Pitch Black | elite_trainer_box | 0.960123 | 0.967532 | -0.007409 |
| Pitch Black | loose_booster_pack | 0.960123 | 0.952148 | 0.007975 |
| Pitch Black | pokemon_center_elite_trainer_box | 0.960123 | 0.952148 | 0.007975 |
| Pitch Black | sleeved_booster_pack | 0.960123 | 0.966434 | -0.00631 |
| Stellar Crown | booster_box | 0.457377 | 0.450273 | 0.007104 |
| Stellar Crown | booster_bundle | 0.457377 | 0.427546 | 0.029831 |
| Stellar Crown | elite_trainer_box | 0.457377 | 0.507965 | -0.050588 |
| Stellar Crown | half_booster_box | 0.457377 | 0.505829 | -0.048452 |
| Stellar Crown | loose_booster_pack | 0.457377 | 0.50186 | -0.044483 |
| Stellar Crown | pokemon_center_elite_trainer_box | 0.457377 | 0.393607 | 0.063771 |
| Stellar Crown | sleeved_booster_pack | 0.457377 | 0.414559 | 0.042818 |
| Chaos Rising | booster_box | 0.645723 | 0.617725 | 0.027998 |
| Chaos Rising | booster_bundle | 0.645723 | 0.620322 | 0.025401 |
| Chaos Rising | elite_trainer_box | 0.645723 | 0.621022 | 0.024702 |
| Chaos Rising | loose_booster_pack | 0.645723 | 0.670106 | -0.024383 |
| Chaos Rising | pokemon_center_elite_trainer_box | 0.645723 | 0.598868 | 0.046855 |
| Chaos Rising | sleeved_booster_pack | 0.645723 | 0.746296 | -0.100573 |
| Paradox Rift | booster_box | 0.520341 | 0.510123 | 0.010218 |
| Paradox Rift | booster_bundle | 0.520341 | 0.606227 | -0.085886 |
| Paradox Rift | elite_trainer_box | 0.520341 | 0.570563 | -0.050222 |
| Paradox Rift | loose_booster_pack | 0.520341 | 0.443457 | 0.076884 |
| Paradox Rift | pokemon_center_elite_trainer_box | 0.520341 | 0.524409 | -0.004068 |
| Paradox Rift | sleeved_booster_pack | 0.520341 | 0.467266 | 0.053075 |
| Perfect Order | booster_box | 0.753677 | 0.718699 | 0.034979 |
| Perfect Order | booster_bundle | 0.753677 | 0.740776 | 0.012901 |
| Perfect Order | elite_trainer_box | 0.753677 | 0.742874 | 0.010803 |
| Perfect Order | loose_booster_pack | 0.753677 | 0.752032 | 0.001646 |
| Perfect Order | pokemon_center_elite_trainer_box | 0.753677 | 0.720413 | 0.033265 |
| Perfect Order | sleeved_booster_pack | 0.753677 | 0.84727 | -0.093593 |
| Ascended Heroes | booster_bundle | 0.867208 | 0.838095 | 0.029112 |
| Ascended Heroes | elite_trainer_box | 0.867208 | 0.822944 | 0.044264 |
| Ascended Heroes | loose_booster_pack | 0.867208 | 0.918182 | -0.050974 |
| Ascended Heroes | pokemon_center_elite_trainer_box | 0.867208 | 0.88961 | -0.022403 |
| Prismatic Evolutions | booster_bundle | 0.650488 | 0.579438 | 0.071049 |
| Prismatic Evolutions | elite_trainer_box | 0.650488 | 0.559625 | 0.090863 |
| Prismatic Evolutions | loose_booster_pack | 0.650488 | 0.835571 | -0.185083 |
| Prismatic Evolutions | pokemon_center_elite_trainer_box | 0.650488 | 0.627317 | 0.023171 |
| Temporal Forces | booster_box | 0.750493 | 0.732718 | 0.017775 |
| Temporal Forces | booster_bundle | 0.750493 | 0.807393 | -0.0569 |
| Temporal Forces | elite_trainer_box | 0.750493 | 0.782626 | -0.032133 |
| Temporal Forces | half_booster_box | 0.750493 | 0.708908 | 0.041585 |
| Temporal Forces | loose_booster_pack | 0.750493 | 0.740654 | 0.009839 |
| Temporal Forces | pokemon_center_elite_trainer_box | 0.750493 | 0.772242 | -0.021749 |
| Temporal Forces | sleeved_booster_pack | 0.750493 | 0.708908 | 0.041585 |
| Mega Evolution | booster_box | 0.525478 | 0.553534 | -0.028056 |
| Mega Evolution | booster_bundle | 0.525478 | 0.522149 | 0.003329 |
| Mega Evolution | elite_trainer_box | 0.525478 | 0.504084 | 0.021395 |
| Mega Evolution | half_booster_box | 0.525478 | 0.557503 | -0.032024 |
| Mega Evolution | loose_booster_pack | 0.525478 | 0.541629 | -0.016151 |
| Mega Evolution | pokemon_center_elite_trainer_box | 0.525478 | 0.469725 | 0.055754 |
| Mega Evolution | sleeved_booster_pack | 0.525478 | 0.529725 | -0.004246 |
| Obsidian Flames | booster_box | 0.196294 | 0.235553 | -0.039259 |
| Obsidian Flames | booster_bundle | 0.196294 | 0.226462 | -0.030168 |
| Obsidian Flames | elite_trainer_box | 0.196294 | 0.197091 | -0.000797 |
| Obsidian Flames | loose_booster_pack | 0.196294 | 0.206981 | -0.010687 |
| Obsidian Flames | pokemon_center_elite_trainer_box | 0.196294 | 0.147553 | 0.048741 |
| Obsidian Flames | sleeved_booster_pack | 0.196294 | 0.164124 | 0.03217 |
| White Flare | booster_bundle | 0.385622 | 0.347497 | 0.038126 |
| White Flare | elite_trainer_box | 0.385622 | 0.360317 | 0.025305 |
| White Flare | loose_booster_pack | 0.385622 | 0.387179 | -0.001557 |
| White Flare | pokemon_center_elite_trainer_box | 0.385622 | 0.447497 | -0.061874 |
| Twilight Masquerade | booster_box | 0.580833 | 0.60621 | -0.025377 |
| Twilight Masquerade | booster_bundle | 0.580833 | 0.617033 | -0.0362 |
| Twilight Masquerade | elite_trainer_box | 0.580833 | 0.555844 | 0.024989 |
| Twilight Masquerade | half_booster_box | 0.580833 | 0.566528 | 0.014306 |
| Twilight Masquerade | loose_booster_pack | 0.580833 | 0.574464 | 0.006369 |
| Twilight Masquerade | pokemon_center_elite_trainer_box | 0.580833 | 0.610972 | -0.030139 |
| Twilight Masquerade | sleeved_booster_pack | 0.580833 | 0.534782 | 0.046052 |
| Scarlet and Violet 151 | booster_bundle | 0.445335 | 0.351355 | 0.093979 |
| Scarlet and Violet 151 | elite_trainer_box | 0.445335 | 0.568139 | -0.122804 |
| Scarlet and Violet 151 | loose_booster_pack | 0.445335 | 0.308065 | 0.137269 |
| Scarlet and Violet 151 | pokemon_center_elite_trainer_box | 0.445335 | 0.55378 | -0.108445 |
| Destined Rivals | booster_box | 0.376326 | 0.403332 | -0.027007 |
| Destined Rivals | booster_bundle | 0.376326 | 0.340562 | 0.035764 |
| Destined Rivals | elite_trainer_box | 0.376326 | 0.330072 | 0.046253 |
| Destined Rivals | half_booster_box | 0.376326 | 0.439047 | -0.062721 |
| Destined Rivals | loose_booster_pack | 0.376326 | 0.327935 | 0.04839 |
| Destined Rivals | pokemon_center_elite_trainer_box | 0.376326 | 0.425713 | -0.049388 |
| Destined Rivals | sleeved_booster_pack | 0.376326 | 0.367618 | 0.008708 |
| Surging Sparks | booster_box | 0.297391 | 0.299337 | -0.001946 |
| Surging Sparks | booster_bundle | 0.297391 | 0.301502 | -0.004111 |
| Surging Sparks | elite_trainer_box | 0.297391 | 0.289264 | 0.008127 |
| Surging Sparks | half_booster_box | 0.297391 | 0.263623 | 0.033768 |
| Surging Sparks | loose_booster_pack | 0.297391 | 0.299337 | -0.001946 |
| Surging Sparks | pokemon_center_elite_trainer_box | 0.297391 | 0.293623 | 0.003768 |
| Surging Sparks | sleeved_booster_pack | 0.297391 | 0.335052 | -0.03766 |
| Paldean Fates | booster_bundle | 0.117797 | 0.066154 | 0.051643 |
| Paldean Fates | elite_trainer_box | 0.117797 | 0.144242 | -0.026445 |
| Paldean Fates | loose_booster_pack | 0.117797 | 0.157063 | -0.039266 |
| Paldean Fates | pokemon_center_elite_trainer_box | 0.117797 | 0.10373 | 0.014068 |

# LEAVE-ONE-FAMILY-OUT STABILITY

| Omitted family | Overlap N | Spearman | Top-5 overlap | Mean abs movement | Max movement |
|---|---:|---:|---:|---:|---:|
| booster_box | 22 | 0.98419 | 5 | 0.818182 | 2 |
| booster_bundle | 22 | 0.98419 | 5 | 0.818182 | 3 |
| elite_trainer_box | 22 | 0.95144 | 5 | 1.363636 | 6 |
| enhanced_booster_box | 22 | 1.0 | 5 | 0.0 | 0 |
| half_booster_box | 22 | 0.98419 | 5 | 0.636364 | 3 |
| loose_booster_pack | 22 | 0.960474 | 4 | 1.363636 | 4 |
| pokemon_center_elite_trainer_box | 22 | 0.953698 | 5 | 1.272727 | 5 |
| sleeved_booster_pack | 22 | 0.986448 | 4 | 0.636364 | 3 |

# 189-CANDIDATE SENSITIVITY

All 189 pre-registered configurations remain in JSON. The reasonable-gate robustness subset contains 84 configurations and reports top-three/top-five frequencies for every set.

# PACK-RANKING COMPARISON

Descriptive only: overlap N=22, Spearman=0.564088, top-five overlap=3, mean absolute movement=5.681818, maximum movement=14.

# PROMOTION GATE

Methodology version: `set_rip_consensus_v1_mean_sku_mean_family_unshrunk_cov2_cohort3_missing_omit`

| Check | Observed | Required | Status |
|---|---|---|---|
| runAuthority | `{"matchRate": 1.0}` | `{"matchRate": 1.0}` | PASS |
| canonicalVersions | `{"matchRate": 1.0, "versions": {"collectorAppeal": "collector_appeal_v5_contextual_roster_h_only_d_baseline_up4_down2", "financialRip": "financial_rip_v3_outcome_profile_25_20_15_25_10_5", "overallRip": "overall_rip_v9_90_financial_v3_10_collector_appeal_v5"}}` | `{"matchRate": 1.0}` | PASS |
| setCoverage | `{"coverageRate": 1.0, "rankableSetCount": 22, "rankedSetCount": 22}` | `{"minimumCoverageRate": 0.9, "minimumRankableSetCount": 20}` | PASS |
| familyCohortQuality | `{"ineligibleParticipatingFamilies": []}` | `{"minimumRepresentedSets": 3, "sensitivityRepresentedSets": 5}` | PASS |
| deferredCoverage | `{"enhancedBoosterBoxRepresentedSets": 2, "expandedEtb": true, "expandedPokemonCenterEtb": true, "halfBoosterBox": true}` | `{"enhancedBoosterBox": "required only if >=3 represented sets", "expandedEtb": true, "expandedPokemonCenterEtb": true, "halfBoosterBox": "meaningful new artifact-backed coverage"}` | PASS |
| leaveOneFamilyOutStability | `{"informativeOmissions": 7, "maximumIndividualRankMovement": 6, "maximumMeanAbsoluteRankMovement": 1.363636, "minimumSpearman": 0.95144, "minimumTop5Overlap": 4}` | `{"maximumIndividualRankMovement": 6, "maximumMeanAbsoluteRankMovement": 2.0, "minimumSpearman": 0.85, "minimumTop5Overlap": 4}` | PASS |
| representativeSensitivity | `{"comparisons": {"best": {"maximumRankMovement": 1, "meanAbsoluteRankMovement": 0.090909, "overlapN": 22, "spearman": 0.998871, "top3Overlap": 2, "top5Overlap": 5}, "coverage3": {"maximumRankMovement": 0, "meanAbsoluteRankMovement": 0.0, "overlapN": 22, "spearman": 1.0, "top3Overlap": 3, "top5Overlap": 5}, "familyCohort5": {"maximumRankMovement": 0, "meanAbsoluteRankMovement": 0.0, "overlapN": 22, "spearman": 1.0, "top3Overlap": 3, "top5Overlap": 5}, "groupBalanced": {"maximumRankMovement": 2, "meanAbsoluteRankMovement": 0.636364, "overlapN": 22, "spearman": 0.989836, "top3Overlap": 3, "top5Overlap": 5}, "median": {"maximumRankMovement": 0, "meanAbsoluteRankMovement": 0.0, "overlapN": 22, "spearman": 1.0, "top3Overlap": 3, "top5Overlap": 5}}, "warningComparisons": []}` | `{"bestAndMedianMinimumSpearman": 0.85, "bestAndMedianMinimumTop5Overlap": 4, "requiredDiagnostics": ["coverage3", "familyCohort5", "groupBalanced"]}` | PASS |
| familyCountFairness | `{"spearmanCoverageVsSetRip": -0.008981}` | `{"absoluteSpearmanReviewThreshold": 0.6}` | PASS |
| multiSkuInvariant | `{"oneVotePerSetFamily": true}` | `{"oneVotePerSetFamily": true}` | PASS |

Overall: **METHODOLOGY_READY_FOR_PROMOTION_REVIEW**

# FROZEN BASELINE

As of 2026-08-17: 22 of 22 ranked sets clear the coverage gate. The full ordering and scores are recorded in JSON.

# POST-COVERAGE WORKFLOW

1. Rebuild normal product-family Rankings after normal artifact-backed simulations populate deferred products.
2. Run this same frozen research harness without changing its methodology version or gate constants.
3. Evaluate the pre-registered promotion gate.
4. Compare before/after family coverage and descriptive ranking movement.
5. Report PASS, FAIL, or REVIEW REQUIRED without changing methodology during the validation run.
6. Return results for human promotion review; the harness cannot publish or promote itself.

# HISTORICAL EVIDENCE

HISTORICAL_EVIDENCE_INSUFFICIENT

No stored historical product-family projections with current canonical model versions were found; historical Monte Carlo was not rerun.

# PRIOR RESEARCH INVALIDATION

INVALIDATED_BY_RUN_AUTHORITY_BUG

The prior numeric artifacts selected sealed-product runs through one market date instead of each ranked target's calculation_run_id. The pre-registered 189-configuration methodology is unchanged; all numeric findings were recomputed.

# KNOWN LIMITATIONS

- Half Booster Box and Enhanced Booster Box currently have no or insufficient canonical coverage.
- Verified deferred products are missing evidence, not poor performance.
- 22 sets currently clear the leading candidate's gate; this is research coverage, not a validated public Set RIP cohort.
- Related pack formats may count correlated evidence more than once; group-balanced results are retained as a sensitivity architecture.

# PROMOTION STATUS

METHODOLOGY_READY_FOR_PROMOTION_REVIEW
