# Chilling Reign Bucket Classification Ledger (Project 6.1.1)

## Purpose

This ledger proves every eligible non-reverse rare-family Chilling Reign (`swsh6`) variant maps to exactly one simulator bucket before probability modeling.

- Runtime remains disabled: `SLOT_SCHEMA_RUNTIME_ENABLED = False`
- No `RARE_SLOT_PROBABILITY` is introduced in this project
- Reverse-holo variants are excluded from rare-slot outcome buckets

## Coverage Summary

| Bucket | Variant Count |
|---|---:|
| rare | 23 |
| holo rare | 24 |
| regular v | 15 |
| regular vmax | 8 |
| full art v | 16 |
| full art trainer | 13 |
| alternate art v | 10 |
| alternate art vmax | 3 |
| rainbow trainer | 12 |
| rainbow vmax | 8 |
| gold secret rare | 12 |
| **TOTAL** | **144** |

- eligible_non_reverse_rare_family_variants: **144**
- mapped_variants: **144**
- unmapped_variants: **0**
- overlapping_variants: **0**
- reconciliation: earlier planning target of 132 conflicts with the listed per-bucket counts; these validated counts sum to 144.

## Ambiguous Name Examples

| Card Name | Card Number | pokemon_tcg_api_id | Rarity | Printing | Resolved Bucket | Matching Rule |
|---|---|---|---|---|---|---|
| Blaziken V | 020/198 | swsh6-20 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Blaziken V (Full Art) | 161/198 | swsh6-161 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Blaziken VMAX | 021/198 | swsh6-21 | Ultra Rare | holo | regular vmax | rarity='Ultra Rare' + card_number<=159 + name contains 'VMAX' + printing_type='holo' |
| Blaziken VMAX (Secret) | 200/198 | swsh6-200 | Secret Rare | holo | rainbow vmax | rarity='Secret Rare' + card_number 199-209 + name contains 'VMAX' and not 'Alternate' + printing_type='holo' |
| Blaziken VMAX (Alternate Art Secret) | 201/198 | swsh6-201 | Secret Rare | holo | alternate art vmax | rarity='Secret Rare' + name contains 'Alternate Art Secret' and 'VMAX' + printing_type='holo' |
| Snorlax (Secret) | 224/198 | swsh6-224 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |

## Full Eligible Variant Ledger

### rare

| Card Name | Card Number | pokemon_tcg_api_id | Rarity | Printing Type | Resolved Bucket | Matching Rule |
|---|---|---|---|---|---|---|
| Abomasnow | 010/198 | swsh6-10 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Sawsbuck | 012/198 | swsh6-12 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Tsareena | 015/198 | swsh6-15 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Volcarona | 024/198 | swsh6-24 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Walrein | 039/198 | swsh6-39 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Ampharos | 049/198 | swsh6-49 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Zebstrika | 051/198 | swsh6-51 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Banette | 063/198 | swsh6-63 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Golurk | 066/198 | swsh6-66 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Slurpuff | 068/198 | swsh6-68 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Malamar | 070/198 | swsh6-70 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Dugtrio | 077/198 | swsh6-77 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Galarian Sirfetch'd | 079/198 | swsh6-79 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Gallade | 081/198 | swsh6-81 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Passimian | 088/198 | swsh6-88 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Weezing | 095/198 | swsh6-95 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Galarian Weezing | 096/198 | swsh6-96 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Seviper | 102/198 | swsh6-102 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Spiritomb | 103/198 | swsh6-103 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Scolipede | 107/198 | swsh6-107 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Aggron | 111/198 | swsh6-111 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Zangoose | 120/198 | swsh6-120 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |
| Kecleon | 122/198 | swsh6-122 | Rare | non-holo | rare | rarity='Rare' + printing_type='non-holo' |

### holo rare

| Card Name | Card Number | pokemon_tcg_api_id | Rarity | Printing Type | Resolved Bucket | Matching Rule |
|---|---|---|---|---|---|---|
| Beedrill | 003/198 | swsh6-3 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Rillaboom | 018/198 | swsh6-18 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Zarude | 019/198 | swsh6-19 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Cinderace | 028/198 | swsh6-28 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Weavile | 031/198 | swsh6-31 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Froslass | 036/198 | swsh6-36 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Tapu Fini | 040/198 | swsh6-40 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Inteleon | 043/198 | swsh6-43 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Rapid Strike Urshifu | 044/198 | swsh6-44 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Thundurus | 052/198 | swsh6-52 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Gengar | 057/198 | swsh6-57 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Gardevoir | 061/198 | swsh6-61 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Cresselia | 064/198 | swsh6-64 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Hatterene | 073/198 | swsh6-73 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Galarian Runerigus | 083/198 | swsh6-83 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Lycanroc | 087/198 | swsh6-87 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Grapploct | 092/198 | swsh6-92 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Galarian Slowking | 098/198 | swsh6-98 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Single Strike Urshifu | 108/198 | swsh6-108 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Cobalion | 114/198 | swsh6-114 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Tauros | 115/198 | swsh6-115 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Porygon-Z | 118/198 | swsh6-118 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Shaymin | 123/198 | swsh6-123 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |
| Greedent | 128/198 | swsh6-128 | Holo Rare | holo | holo rare | rarity='Holo Rare' + printing_type='holo' |

### regular v

| Card Name | Card Number | pokemon_tcg_api_id | Rarity | Printing Type | Resolved Bucket | Matching Rule |
|---|---|---|---|---|---|---|
| Celebi V | 007/198 | swsh6-7 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Blaziken V | 020/198 | swsh6-20 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Volcanion V | 025/198 | swsh6-25 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Ice Rider Calyrex V | 045/198 | swsh6-45 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Zeraora V | 053/198 | swsh6-53 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Galarian Articuno V | 058/198 | swsh6-58 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Shadow Rider Calyrex V | 074/198 | swsh6-74 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Galarian Zapdos V | 080/198 | swsh6-80 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Sandaconda V | 089/198 | swsh6-89 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Galarian Moltres V | 097/198 | swsh6-97 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Galarian Slowking V | 099/198 | swsh6-99 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Liepard V | 104/198 | swsh6-104 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Metagross V | 112/198 | swsh6-112 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Blissey V | 119/198 | swsh6-119 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |
| Tornadus V | 124/198 | swsh6-124 | Ultra Rare | holo | regular v | rarity='Ultra Rare' + card_number<=159 + name endswith(' V') + printing_type='holo' |

### regular vmax

| Card Name | Card Number | pokemon_tcg_api_id | Rarity | Printing Type | Resolved Bucket | Matching Rule |
|---|---|---|---|---|---|---|
| Celebi VMAX | 008/198 | swsh6-8 | Ultra Rare | holo | regular vmax | rarity='Ultra Rare' + card_number<=159 + name contains 'VMAX' + printing_type='holo' |
| Blaziken VMAX | 021/198 | swsh6-21 | Ultra Rare | holo | regular vmax | rarity='Ultra Rare' + card_number<=159 + name contains 'VMAX' + printing_type='holo' |
| Ice Rider Calyrex VMAX | 046/198 | swsh6-46 | Ultra Rare | holo | regular vmax | rarity='Ultra Rare' + card_number<=159 + name contains 'VMAX' + printing_type='holo' |
| Shadow Rider Calyrex VMAX | 075/198 | swsh6-75 | Ultra Rare | holo | regular vmax | rarity='Ultra Rare' + card_number<=159 + name contains 'VMAX' + printing_type='holo' |
| Sandaconda VMAX | 090/198 | swsh6-90 | Ultra Rare | holo | regular vmax | rarity='Ultra Rare' + card_number<=159 + name contains 'VMAX' + printing_type='holo' |
| Galarian Slowking VMAX | 100/198 | swsh6-100 | Ultra Rare | holo | regular vmax | rarity='Ultra Rare' + card_number<=159 + name contains 'VMAX' + printing_type='holo' |
| Metagross VMAX | 113/198 | swsh6-113 | Ultra Rare | holo | regular vmax | rarity='Ultra Rare' + card_number<=159 + name contains 'VMAX' + printing_type='holo' |
| Tornadus VMAX | 125/198 | swsh6-125 | Ultra Rare | holo | regular vmax | rarity='Ultra Rare' + card_number<=159 + name contains 'VMAX' + printing_type='holo' |

### full art v

| Card Name | Card Number | pokemon_tcg_api_id | Rarity | Printing Type | Resolved Bucket | Matching Rule |
|---|---|---|---|---|---|---|
| Celebi V (Full Art) | 160/198 | swsh6-160 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Blaziken V (Full Art) | 161/198 | swsh6-161 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Volcanion V (Full Art) | 162/198 | swsh6-162 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Ice Rider Calyrex V (Full Art) | 163/198 | swsh6-163 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Zeraora V (Full Art) | 165/198 | swsh6-165 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Galarian Rapidash V (Full Art) | 167/198 | swsh6-167 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Galarian Articuno V (Full Art) | 169/198 | swsh6-169 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Shadow Rider Calyrex V (Full Art) | 171/198 | swsh6-171 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Galarian Zapdos V (Full Art) | 173/198 | swsh6-173 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Sandaconda V (Full Art) | 175/198 | swsh6-175 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Galarian Moltres V (Full Art) | 176/198 | swsh6-176 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Galarian Slowking V (Full Art) | 178/198 | swsh6-178 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Liepard V (Full Art) | 180/198 | swsh6-180 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Metagross V (Full Art) | 181/198 | swsh6-181 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Blissey V (Full Art) | 182/198 | swsh6-182 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |
| Tornadus V (Full Art) | 184/198 | swsh6-184 | Ultra Rare | holo | full art v | rarity='Ultra Rare' + card_number 160-185 + name contains '(Full Art)' and not 'Alternate' + printing_type='holo' |

### full art trainer

| Card Name | Card Number | pokemon_tcg_api_id | Rarity | Printing Type | Resolved Bucket | Matching Rule |
|---|---|---|---|---|---|---|
| Agatha (Full Art) | 186/198 | swsh6-186 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |
| Avery (Full Art) | 187/198 | swsh6-187 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |
| Brawly (Full Art) | 188/198 | swsh6-188 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |
| Caitlin (Full Art) | 189/198 | swsh6-189 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |
| Doctor (Full Art) | 190/198 | swsh6-190 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |
| Flannery (Full Art) | 191/198 | swsh6-191 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |
| Honey (Full Art) | 192/198 | swsh6-192 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |
| Karen's Conviction (Full Art) | 193/198 | swsh6-193 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |
| Klara (Full Art) | 194/198 | swsh6-194 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |
| Melony (Full Art) | 195/198 | swsh6-195 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |
| Peonia (Full Art) | 196/198 | swsh6-196 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |
| Peony (Full Art) | 197/198 | swsh6-197 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |
| Siebold (Full Art) | 198/198 | swsh6-198 | Ultra Rare | holo | full art trainer | rarity='Ultra Rare' + card_number 186-198 + printing_type='holo' |

### alternate art v

| Card Name | Card Number | pokemon_tcg_api_id | Rarity | Printing Type | Resolved Bucket | Matching Rule |
|---|---|---|---|---|---|---|
| Ice Rider Calyrex V (Alternate Full Art) | 164/198 | swsh6-164 | Ultra Rare | holo | alternate art v | rarity='Ultra Rare' + name contains '(Alternate Full Art)' + printing_type='holo' |
| Zeraora V (Alternate Full Art) | 166/198 | swsh6-166 | Ultra Rare | holo | alternate art v | rarity='Ultra Rare' + name contains '(Alternate Full Art)' + printing_type='holo' |
| Galarian Rapidash V (Alternate Full Art) | 168/198 | swsh6-168 | Ultra Rare | holo | alternate art v | rarity='Ultra Rare' + name contains '(Alternate Full Art)' + printing_type='holo' |
| Galarian Articuno V (Alternate Full Art) | 170/198 | swsh6-170 | Ultra Rare | holo | alternate art v | rarity='Ultra Rare' + name contains '(Alternate Full Art)' + printing_type='holo' |
| Shadow Rider Calyrex V (Alternate Full Art) | 172/198 | swsh6-172 | Ultra Rare | holo | alternate art v | rarity='Ultra Rare' + name contains '(Alternate Full Art)' + printing_type='holo' |
| Galarian Zapdos V (Alternate Full Art) | 174/198 | swsh6-174 | Ultra Rare | holo | alternate art v | rarity='Ultra Rare' + name contains '(Alternate Full Art)' + printing_type='holo' |
| Galarian Moltres V (Alternate Full Art) | 177/198 | swsh6-177 | Ultra Rare | holo | alternate art v | rarity='Ultra Rare' + name contains '(Alternate Full Art)' + printing_type='holo' |
| Galarian Slowking V (Alternate Full Art) | 179/198 | swsh6-179 | Ultra Rare | holo | alternate art v | rarity='Ultra Rare' + name contains '(Alternate Full Art)' + printing_type='holo' |
| Blissey V (Alternate Full Art) | 183/198 | swsh6-183 | Ultra Rare | holo | alternate art v | rarity='Ultra Rare' + name contains '(Alternate Full Art)' + printing_type='holo' |
| Tornadus V (Alternate Full Art) | 185/198 | swsh6-185 | Ultra Rare | holo | alternate art v | rarity='Ultra Rare' + name contains '(Alternate Full Art)' + printing_type='holo' |

### alternate art vmax

| Card Name | Card Number | pokemon_tcg_api_id | Rarity | Printing Type | Resolved Bucket | Matching Rule |
|---|---|---|---|---|---|---|
| Blaziken VMAX (Alternate Art Secret) | 201/198 | swsh6-201 | Secret Rare | holo | alternate art vmax | rarity='Secret Rare' + name contains 'Alternate Art Secret' and 'VMAX' + printing_type='holo' |
| Ice Rider Calyrex VMAX (Alternate Art Secret) | 203/198 | swsh6-203 | Secret Rare | holo | alternate art vmax | rarity='Secret Rare' + name contains 'Alternate Art Secret' and 'VMAX' + printing_type='holo' |
| Shadow Rider Calyrex VMAX (Alternate Art Secret) | 205/198 | swsh6-205 | Secret Rare | holo | alternate art vmax | rarity='Secret Rare' + name contains 'Alternate Art Secret' and 'VMAX' + printing_type='holo' |

### rainbow trainer

| Card Name | Card Number | pokemon_tcg_api_id | Rarity | Printing Type | Resolved Bucket | Matching Rule |
|---|---|---|---|---|---|---|
| Agatha (Secret) | 210/198 | swsh6-210 | Secret Rare | holo | rainbow trainer | rarity='Secret Rare' + card_number 210-221 + printing_type='holo' |
| Avery (Secret) | 211/198 | swsh6-211 | Secret Rare | holo | rainbow trainer | rarity='Secret Rare' + card_number 210-221 + printing_type='holo' |
| Brawly (Secret) | 212/198 | swsh6-212 | Secret Rare | holo | rainbow trainer | rarity='Secret Rare' + card_number 210-221 + printing_type='holo' |
| Caitlin (Secret) | 213/198 | swsh6-213 | Secret Rare | holo | rainbow trainer | rarity='Secret Rare' + card_number 210-221 + printing_type='holo' |
| Doctor (Secret) | 214/198 | swsh6-214 | Secret Rare | holo | rainbow trainer | rarity='Secret Rare' + card_number 210-221 + printing_type='holo' |
| Flannery (Secret) | 215/198 | swsh6-215 | Secret Rare | holo | rainbow trainer | rarity='Secret Rare' + card_number 210-221 + printing_type='holo' |
| Karen's Conviction (Secret) | 216/198 | swsh6-216 | Secret Rare | holo | rainbow trainer | rarity='Secret Rare' + card_number 210-221 + printing_type='holo' |
| Klara (Secret) | 217/198 | swsh6-217 | Secret Rare | holo | rainbow trainer | rarity='Secret Rare' + card_number 210-221 + printing_type='holo' |
| Melony (Secret) | 218/198 | swsh6-218 | Secret Rare | holo | rainbow trainer | rarity='Secret Rare' + card_number 210-221 + printing_type='holo' |
| Peonia (Secret) | 219/198 | swsh6-219 | Secret Rare | holo | rainbow trainer | rarity='Secret Rare' + card_number 210-221 + printing_type='holo' |
| Peony (Secret) | 220/198 | swsh6-220 | Secret Rare | holo | rainbow trainer | rarity='Secret Rare' + card_number 210-221 + printing_type='holo' |
| Siebold (Secret) | 221/198 | swsh6-221 | Secret Rare | holo | rainbow trainer | rarity='Secret Rare' + card_number 210-221 + printing_type='holo' |

### rainbow vmax

| Card Name | Card Number | pokemon_tcg_api_id | Rarity | Printing Type | Resolved Bucket | Matching Rule |
|---|---|---|---|---|---|---|
| Celebi VMAX (Secret) | 199/198 | swsh6-199 | Secret Rare | holo | rainbow vmax | rarity='Secret Rare' + card_number 199-209 + name contains 'VMAX' and not 'Alternate' + printing_type='holo' |
| Blaziken VMAX (Secret) | 200/198 | swsh6-200 | Secret Rare | holo | rainbow vmax | rarity='Secret Rare' + card_number 199-209 + name contains 'VMAX' and not 'Alternate' + printing_type='holo' |
| Ice Rider Calyrex VMAX (Secret) | 202/198 | swsh6-202 | Secret Rare | holo | rainbow vmax | rarity='Secret Rare' + card_number 199-209 + name contains 'VMAX' and not 'Alternate' + printing_type='holo' |
| Shadow Rider Calyrex VMAX (Secret) | 204/198 | swsh6-204 | Secret Rare | holo | rainbow vmax | rarity='Secret Rare' + card_number 199-209 + name contains 'VMAX' and not 'Alternate' + printing_type='holo' |
| Sandaconda VMAX (Secret) | 206/198 | swsh6-206 | Secret Rare | holo | rainbow vmax | rarity='Secret Rare' + card_number 199-209 + name contains 'VMAX' and not 'Alternate' + printing_type='holo' |
| Galarian Slowking VMAX (Secret) | 207/198 | swsh6-207 | Secret Rare | holo | rainbow vmax | rarity='Secret Rare' + card_number 199-209 + name contains 'VMAX' and not 'Alternate' + printing_type='holo' |
| Metagross VMAX (Secret) | 208/198 | swsh6-208 | Secret Rare | holo | rainbow vmax | rarity='Secret Rare' + card_number 199-209 + name contains 'VMAX' and not 'Alternate' + printing_type='holo' |
| Tornadus VMAX (Secret) | 209/198 | swsh6-209 | Secret Rare | holo | rainbow vmax | rarity='Secret Rare' + card_number 199-209 + name contains 'VMAX' and not 'Alternate' + printing_type='holo' |

### gold secret rare

| Card Name | Card Number | pokemon_tcg_api_id | Rarity | Printing Type | Resolved Bucket | Matching Rule |
|---|---|---|---|---|---|---|
| Electrode (Secret) | 222/198 | swsh6-222 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |
| Bronzong (Secret) | 223/198 | swsh6-223 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |
| Snorlax (Secret) | 224/198 | swsh6-224 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |
| Echoing Horn (Secret) | 225/198 | swsh6-225 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |
| Fan of Waves (Secret) | 226/198 | swsh6-226 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |
| Fog Crystal (Secret) | 227/198 | swsh6-227 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |
| Rugged Helmet (Secret) | 228/198 | swsh6-228 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |
| Urn of Vitality (Secret) | 229/198 | swsh6-229 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |
| Welcoming Lantern (Secret) | 230/198 | swsh6-230 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |
| Water Energy (Secret) | 231/198 | swsh6-231 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |
| Psychic Energy (Secret) | 232/198 | swsh6-232 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |
| Fighting Energy (Secret) | 233/198 | swsh6-233 | Secret Rare | holo | gold secret rare | rarity='Secret Rare' + card_number 222-233 + printing_type='holo' |

## Residual Rare Rule

`rare` is residual-capable. It does not require a direct source row. Once non-rare outcomes are source-backed, `P(rare)` is the remainder after subtracting all other rare-slot outcome probabilities from 1.