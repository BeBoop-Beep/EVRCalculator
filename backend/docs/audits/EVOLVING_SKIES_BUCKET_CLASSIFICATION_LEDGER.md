# Evolving Skies Bucket Classification Ledger (Project 6.1)

## Purpose

This ledger proves that every eligible non-reverse rare-family card/variant in Evolving Skies (`swsh7`)
belongs to **exactly one** simulator outcome bucket before pull-rate probabilities are added.

**Scope:** Non-reverse rare-family variants only (i.e., variants not marked `printing_type = reverse-holo`).  
**Runtime:** `SLOT_SCHEMA_RUNTIME_ENABLED = False` — this ledger is read-only documentation.  
**Probabilities:** No `RARE_SLOT_PROBABILITY` added. Buckets are defined; rates are not.

---

## Critical Modeling Rule: Rarity Alone Is Insufficient

TCGPlayer and Supabase rarity labels (`Ultra Rare`, `Secret Rare`) are broad population labels,
not final simulator outcome buckets. Multiple distinct simulator outcomes share the same rarity label.

| Rarity Label  | Simulator Outcomes It Covers                                             |
|---------------|--------------------------------------------------------------------------|
| Rare          | rare                                                                     |
| Holo Rare     | holo rare                                                                |
| Ultra Rare    | regular v, regular vmax, full art v, full art trainer, alternate art v   |
| Secret Rare   | alternate art vmax, rainbow trainer, rainbow vmax, gold secret rare      |

**Resolution requires:** `rarity` + `card_number` + `name` (suffixes and parentheticals).

---

## Bucket Classification Rules

Each bucket is resolved by the filter set in `SLOT_SCHEMA_OUTCOME_POOL_MAPPING`.
Reverse-holo variants are excluded from all buckets (`include_reverse_variants = False`).

### 1. `rare`
- **Rarity:** Rare  
- **Printing type:** non-holo  
- **Card number:** any (no range filter needed; Rare rarity is unambiguous)  
- **Name filter:** none  
- **Identifiability:** DB fields only  
- **Pool count:** 19 variants  
- **Residual note:** `rare` is the residual bucket — its pull probability is `1 - sum(all other rare-slot outcome probabilities)` once those are source-backed. No direct source row is required for `rare`.

### 2. `holo rare`
- **Rarity:** Holo Rare  
- **Printing type:** holo  
- **Card number:** any  
- **Name filter:** none  
- **Identifiability:** DB fields only  
- **Pool count:** 20 variants  

### 3. `regular v`
- **Rarity:** Ultra Rare  
- **Printing type:** holo  
- **Card number:** ≤ 203 (within printed set)  
- **Name filter:** ends with ` V` (exactly — not `VMAX`, not `(Full Art)`)  
- **Identifiability:** rarity + card_number + name pattern  
- **Pool count:** 18 variants  

### 4. `regular vmax`
- **Rarity:** Ultra Rare  
- **Printing type:** holo  
- **Card number:** ≤ 203 (within printed set)  
- **Name filter:** contains `VMAX`  
- **Identifiability:** rarity + card_number + name  
- **Pool count:** 15 variants  

### 5. `full art v`
- **Rarity:** Ultra Rare  
- **Printing type:** holo  
- **Card number:** 166–198  
- **Name filter:** contains `(Full Art)` AND does NOT contain `Alternate`  
- **Identifiability:** rarity + card_number range + name  
- **Pool count:** 22 variants  

### 6. `full art trainer`
- **Rarity:** Ultra Rare  
- **Printing type:** holo  
- **Card number:** 199–203  
- **Name filter:** none (card number range is sufficient)  
- **Identifiability:** rarity + card_number range  
- **Pool count:** 5 variants  

### 7. `alternate art v`
- **Rarity:** Ultra Rare  
- **Printing type:** holo  
- **Card number:** any  
- **Name filter:** contains `(Alternate Full Art)`  
- **Identifiability:** rarity + name  
- **Pool count:** 11 variants  

### 8. `alternate art vmax`
- **Rarity:** Secret Rare  
- **Printing type:** holo  
- **Card number:** any  
- **Name filter:** contains `Alternate Art Secret` AND contains `VMAX`  
- **Identifiability:** rarity + name  
- **Pool count:** 6 variants  

### 9. `rainbow trainer`
- **Rarity:** Secret Rare  
- **Printing type:** holo  
- **Card number:** 221–225  
- **Name filter:** none  
- **Identifiability:** rarity + card_number range  
- **Pool count:** 5 variants  

### 10. `rainbow vmax`
- **Rarity:** Secret Rare  
- **Printing type:** holo  
- **Card number:** 204–220  
- **Name filter:** contains `VMAX` AND does NOT contain `Alternate`  
- **Identifiability:** rarity + card_number range + name  
- **Pool count:** 11 variants  

### 11. `gold secret rare`
- **Rarity:** Secret Rare  
- **Printing type:** holo  
- **Card number:** 226–237  
- **Name filter:** none (card number range is sufficient)  
- **Identifiability:** rarity + card_number range  
- **Pool count:** 12 variants  

---

## Coverage Validation

| Bucket              | Variant Count |
|---------------------|---------------|
| rare                | 19            |
| holo rare           | 20            |
| regular v           | 18            |
| regular vmax        | 15            |
| full art v          | 22            |
| full art trainer    | 5             |
| alternate art v     | 11            |
| alternate art vmax  | 6             |
| rainbow trainer     | 5             |
| rainbow vmax        | 11            |
| gold secret rare    | 12            |
| **TOTAL**           | **144**       |

- Eligible non-reverse rare-family variants: **144**
- Mapped variants: **144**
- Unmapped variants: **0**
- Overlapping variants: **0**

Source: `EVOLVING_SKIES_OUTCOME_POOL_MAPPING_AUDIT` in `evolvingSkies.py`,
applied to Supabase `cards` + `card_variants` (read-only, swsh7).

---

## Ambiguous Name Family: Umbreon Examples

The Umbreon card family illustrates why rarity alone cannot determine the simulator bucket.
All six Umbreon rare-family variants share the same Pokémon species, yet each resolves
to a different bucket through rarity + card_number + name rules.

| Card Name                          | Card # | Rarity      | Printing   | Resolved Bucket    | Matching Rule                                                                     |
|------------------------------------|--------|-------------|------------|--------------------|-----------------------------------------------------------------------------------|
| Umbreon V                          | 094    | Ultra Rare  | holo       | **regular v**      | Ultra Rare + number ≤ 203 + name ends with ` V`                                   |
| Umbreon V (Full Art)               | 179    | Ultra Rare  | holo       | **full art v**     | Ultra Rare + number 166–198 + name contains `(Full Art)`, not `Alternate`         |
| Umbreon V (Alternate Full Art)     | 188    | Ultra Rare  | holo       | **alternate art v**| Ultra Rare + name contains `(Alternate Full Art)`                                 |
| Umbreon VMAX                       | 095    | Ultra Rare  | holo       | **regular vmax**   | Ultra Rare + number ≤ 203 + name contains `VMAX`                                 |
| Umbreon VMAX                       | 214    | Secret Rare | holo       | **rainbow vmax**   | Secret Rare + number 204–220 + name contains `VMAX`, not `Alternate`             |
| Umbreon VMAX Alternate Art Secret  | 215    | Secret Rare | holo       | **alternate art vmax** | Secret Rare + name contains `Alternate Art Secret` and `VMAX`               |

> **Key insight:** Umbreon V (#094, Ultra Rare) and Umbreon V (Full Art) (#179, Ultra Rare)
> have **identical rarity labels** but resolve to different buckets because of their card number
> and name parenthetical.  
> Similarly, Umbreon VMAX (#095, Ultra Rare) and Umbreon VMAX (#214, Secret Rare) share
> the same card name but differ by rarity and card number, landing in different buckets.

---

## Additional Disambiguation Examples by Bucket

### Gold Secret Rare
| Card Name (example)    | Card # | Rarity      | Printing | Resolved Bucket    | Rule                              |
|------------------------|--------|-------------|----------|--------------------|-----------------------------------|
| Raihan                 | 234    | Secret Rare | holo     | **gold secret rare** | Secret Rare + number 226–237    |

A reverse-holo variant of any Rare card:
| Card Name (example) | Card # | Rarity | Printing     | Resolved Bucket | Rule                                                |
|---------------------|--------|--------|--------------|-----------------|-----------------------------------------------------|
| Applin (Reverse)    | 001    | Rare   | reverse-holo | *(excluded)*    | Reverse-holo variants are excluded from rare slot   |

---

## Rare as Residual Bucket

`rare` does **not** require a direct pull-rate source row.  
Its pull probability is computed as:

```
P(rare) = 1 - P(holo rare) - P(regular v) - P(regular vmax) - P(full art v)
              - P(full art trainer) - P(alternate art v) - P(alternate art vmax)
              - P(rainbow trainer) - P(rainbow vmax) - P(gold secret rare)
```

Once all non-rare rare-slot outcome probabilities are source-backed, `rare` is the remainder.
The bucket is fully classified and ready to receive the residual probability once the other
10 buckets have source-backed rates.

---

## Source Row Readiness

Bucket classification is **complete** (this ledger).  
Pull-rate probability modeling is **blocked** pending source rows for:

- holo rare — no non-overlapping machine-readable source row found
- regular v — no non-overlapping machine-readable source row found
- regular vmax — no non-overlapping machine-readable source row found
- high-rarity outcomes (full art v, alternate art v, alternate art vmax, rainbow vmax, etc.)
  — source data exists as image-only references without structured text extraction

`SLOT_SCHEMA_SOURCE_CONFIDENCE.status = "blocked_incomplete_probability_model"`  
`rare_slot_probability_ready = False`  
`runtime_ready = False`

The user is expected to supply researched, non-overlapping pull-rate rows before
probability modeling proceeds.

---

## Classification Audit Summary

```python
EVOLVING_SKIES_BUCKET_CLASSIFICATION_AUDIT = {
    "status": "complete",
    "source": "Supabase card/variant rows + SLOT_SCHEMA_OUTCOME_POOL_MAPPING",
    "eligible_non_reverse_rare_family_variants": 144,
    "mapped_variants": 144,
    "unmapped_variants": 0,
    "overlapping_variants": 0,
    "ambiguous_name_examples": {
        "Umbreon V (#094)":                         "regular v",
        "Umbreon V (Full Art) (#179)":              "full art v",
        "Umbreon V (Alternate Full Art) (#188)":    "alternate art v",
        "Umbreon VMAX (#095)":                      "regular vmax",
        "Umbreon VMAX (#214, Secret Rare)":         "rainbow vmax",
        "Umbreon VMAX Alternate Art Secret (#215)": "alternate art vmax",
    },
    "notes": (
        "Rarity alone is insufficient; bucket resolution uses rarity + card_number + name. "
        "rare is residual-capable and does not require a direct source row."
    ),
}
```
