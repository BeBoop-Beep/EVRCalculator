# PURE_TREATMENT Three-Level V1 — Double Rare / Ultra Rare / SIR

Decision token: `PURE_TREATMENT_THREE_LEVEL_PILOT_ESTIMATED`

## Scarcity-controlled treatment ladder

Using Ultra Rare as the reference treatment:

- **Double Rare vs Ultra Rare:** **1.076x**
  - whole-subject bootstrap 95% interval: **0.580x–2.252x**
- **Ultra Rare:** **1.000x reference**
- **SIR vs Ultra Rare:** **4.862x**
  - whole-subject bootstrap 95% interval: **2.205x–7.150x**
- **SIR vs Double Rare:** **4.517x**
  - whole-subject bootstrap 95% interval: **1.113x–10.932x**

The Double Rare / Ultra Rare interval crosses 1.0 and does not establish a
stable pure-treatment ordering between those two labels. The SIR contrasts remain
positive after exact pull-scarcity and frozen Artist controls.

## Temporal stability

- early Double / Ultra: **1.089x**
- late Double / Ultra: **1.064x**
- early SIR / Ultra: **4.856x**
- late SIR / Ultra: **4.866x**
- early SIR / Double: **4.460x**
- late SIR / Double: **4.571x**
- all contrast signs stable: **true**

## Era-level adjusted effects

### Mega Evolution

- Double / Ultra: **0.813x**
- SIR / Ultra: **4.475x**
- SIR / Double: **5.505x**

### Scarlet & Violet

- Double / Ultra: **1.425x**
- SIR / Ultra: **5.281x**
- SIR / Double: **3.705x**

The era split reinforces why Double Rare and Ultra Rare should not yet be
assigned a strict global order: their point estimates reverse by era. SIR remains
above both in each era.

## Set-level adjusted effects

| Era | Set | Double / Ultra | SIR / Ultra | SIR / Double |
|---|---|---:|---:|---:|
| Mega Evolution | Chaos Rising | 0.757x | 4.573x | 6.042x |
| Mega Evolution | Mega Evolution | 0.873x | 4.379x | 5.017x |
| Scarlet & Violet | Paldea Evolved | 2.061x | 7.392x | 3.587x |
| Scarlet & Violet | Paradox Rift | 0.986x | 3.773x | 3.828x |

## Influence robustness

- Double / Ultra leave-one-subject-out range: **0.878x–1.348x**
- SIR / Ultra leave-one-subject-out range: **3.912x–5.707x**
- SIR / Double leave-one-subject-out range: **3.121x–5.742x**
- design rank: **4**
- condition number: **8.21**

## Model contract

The joint model uses the same eight subject identities across four Sets and two
eras, with exact three-way shared Near-Mint dates:

`mean log(treatment_NM / UltraRare_NM) ~ treatment dummy + log(UR pull probability / treatment pull probability) + Artist delta`

Subject Appeal cancels by exact matched identity. Frozen V7 Playability also
cancels for every contrast.

## Interpretation

This result supports a connected treatment ladder in which SIR has a material,
persistent treatment/presentation premium while Double Rare and Ultra Rare are
not reliably separable after scarcity is removed. This is research evidence for
relative Treatment Appeal; it is not yet a production 0–100 Treatment score.

Production writes: **ZERO**.
