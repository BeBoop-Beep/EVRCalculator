# Bucket 2C forensic INPUT (evidence only, no analysis, no methodology change)

Read-only from serving history view, generation 39f27e3b-8ff6-472e-a986-77a2c7bcba43, 2026-04-11..2026-09-19 (162 rows/set, 155 for EX era).
All rows chain_segment_id = 0. tracked_value NULL on every Base/Jungle/Fossil/Team Rocket row; EX era tracked_value present (155/155).

market | key | set_id | min idx | max idx | last idx
--- | --- | --- | --- | --- | ---
Base | set:0010d2ec-894e-4c17-855d-5de6ff6fd204 | 0010d2ec-894e-4c17-855d-5de6ff6fd204 | 100.000 | 137.269 | 137.269
Jungle | set:37e1b616-c5f4-4279-83c4-ea8dcdd83c69 | 37e1b616-c5f4-4279-83c4-ea8dcdd83c69 | 54.646 | 100.795 | 87.171
Fossil | set:c86889c9-ea25-4caa-b63c-7aa0b9796da8 | c86889c9-ea25-4caa-b63c-7aa0b9796da8 | 55.402 | 107.094 | 95.155
Team Rocket | set:4f84d317-e15d-4598-bc8d-52baa04b3485 | 4f84d317-e15d-4598-bc8d-52baa04b3485 | 56.243 | 100.571 | 89.059
EX (era, context) | era:a5571ca6-0dae-4366-8d16-d043a9b1659d | - | 100.000 | 135.544 | 135.544

Largest absolute daily index moves (date, index, % vs prior day):
- Base: 2026-04-16 105.268 +3.37; 2026-06-03 112.805 +2.69; 2026-07-14 127.238 +2.48; 2026-07-18 127.609 +2.24; 2026-07-17 124.808 -2.19
- Jungle: 2026-07-16 88.743 +43.54; 2026-07-02 86.747 +38.04; 2026-09-08 89.706 +37.88; 2026-04-29 74.986 +37.22; 2026-09-18 81.812 +35.78
- Fossil: 2026-09-07 107.094 +72.76; 2026-09-06 61.991 -41.12; 2026-06-23 81.334 +40.09; 2026-05-03 76.465 +36.86; 2026-08-14 100.003 +36.50
- Team Rocket: 2026-05-25 76.741 +36.45; 2026-05-12 89.543 +33.68; 2026-08-21 94.488 +25.39; 2026-08-26 89.905 +24.66; 2026-08-24 91.675 +24.24
- EX era: 2026-06-02 110.010 +4.60; 2026-05-26 102.234 -2.54; 2026-05-27 104.460 +2.18; 2026-08-19 131.315 +1.77; 2026-08-02 125.652 +1.72

Last four Jungle rows: 2026-09-19 87.171, 09-18 81.812, 09-17 60.256, 09-16 85.264 (tracked_value NULL, chain_segment_id 0).
Directory tracked value (comparison_value) NULL for Base/Jungle/Fossil/Team Rocket, Gym x2, Neo x4; present for Base Set 2 and every modern set.
