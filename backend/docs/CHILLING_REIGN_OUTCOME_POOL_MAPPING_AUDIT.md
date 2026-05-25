# Chilling Reign Outcome-to-Pool Mapping Audit (Project 5.5.3)

## Scope
Read-only audit from intended rare-slot outcomes to exact Chilling Reign (`swsh6`) Supabase card/variant rows.

Guardrails preserved:
- No `RARE_SLOT_PROBABILITY` was added.
- `SLOT_SCHEMA_RUNTIME_ENABLED` remains `False`.
- No runtime behavior or simulator routing was changed.
- Reverse-holo variants are excluded from rare-slot pools.

## Data Source
- Supabase set row: `1c7aa5c4-c8c9-4ae8-a1eb-d613f7e4b890`
- Tables: `cards`, `card_variants`
- Card rows: `233`
- Variant rows: `369`

## Rare-Slot Outcome Pool Summary

Variant filters used:
- `rare`: `printing_type = non-holo`
- `holo rare`: `printing_type = holo`
- all other outcomes in this audit: `printing_type = holo`
- reverse-holo (`printing_type = reverse-holo`) is excluded from all rare-slot outcomes

Card-level and variant-level counts (separated):

- `rare`: card_count=`23`, variant_count=`23`
- `holo rare`: card_count=`24`, variant_count=`24`
- `regular v`: card_count=`15`, variant_count=`15`
- `regular vmax`: card_count=`8`, variant_count=`8`
- `full art v`: card_count=`16`, variant_count=`16`
- `full art trainer`: card_count=`13`, variant_count=`13`
- `alternate art v`: card_count=`10`, variant_count=`10`
- `alternate art vmax`: card_count=`3`, variant_count=`3`
- `rainbow trainer`: card_count=`12`, variant_count=`12`
- `rainbow vmax`: card_count=`8`, variant_count=`8`
- `gold secret rare`: card_count=`12`, variant_count=`12`

## High-Rarity Identifiability Status

- `full art v`: can be derived from card number ranges + card names.
- `full art trainer`: can be derived from card number ranges.
- `alternate art v`: can be derived from card names.
- `alternate art vmax`: can be derived from card names.
- `rainbow trainer`: can be derived from card number ranges.
- `rainbow vmax`: can be derived from card number ranges + card names.
- `gold secret rare`: can be derived from card number ranges.

Structured DB fields (`special_type`, trainer subtypes) are not populated for this set, so name/range mapping remains required and must be config-controlled.

## Exact Eligible Rows By Intended Outcome

Format:
- `card_number | card_name | card_api_id | eligible_printing_type`

### rare
- `010/198 | Abomasnow | swsh6-10 | non-holo`
- `012/198 | Sawsbuck | swsh6-12 | non-holo`
- `015/198 | Tsareena | swsh6-15 | non-holo`
- `024/198 | Volcarona | swsh6-24 | non-holo`
- `039/198 | Walrein | swsh6-39 | non-holo`
- `049/198 | Ampharos | swsh6-49 | non-holo`
- `051/198 | Zebstrika | swsh6-51 | non-holo`
- `063/198 | Banette | swsh6-63 | non-holo`
- `066/198 | Golurk | swsh6-66 | non-holo`
- `068/198 | Slurpuff | swsh6-68 | non-holo`
- `070/198 | Malamar | swsh6-70 | non-holo`
- `077/198 | Dugtrio | swsh6-77 | non-holo`
- `079/198 | Galarian Sirfetch'd | swsh6-79 | non-holo`
- `081/198 | Gallade | swsh6-81 | non-holo`
- `088/198 | Passimian | swsh6-88 | non-holo`
- `095/198 | Weezing | swsh6-95 | non-holo`
- `096/198 | Galarian Weezing | swsh6-96 | non-holo`
- `102/198 | Seviper | swsh6-102 | non-holo`
- `103/198 | Spiritomb | swsh6-103 | non-holo`
- `107/198 | Scolipede | swsh6-107 | non-holo`
- `111/198 | Aggron | swsh6-111 | non-holo`
- `120/198 | Zangoose | swsh6-120 | non-holo`
- `122/198 | Kecleon | swsh6-122 | non-holo`

### holo rare
- `003/198 | Beedrill | swsh6-3 | holo`
- `018/198 | Rillaboom | swsh6-18 | holo`
- `019/198 | Zarude | swsh6-19 | holo`
- `028/198 | Cinderace | swsh6-28 | holo`
- `031/198 | Weavile | swsh6-31 | holo`
- `036/198 | Froslass | swsh6-36 | holo`
- `040/198 | Tapu Fini | swsh6-40 | holo`
- `043/198 | Inteleon | swsh6-43 | holo`
- `044/198 | Rapid Strike Urshifu | swsh6-44 | holo`
- `052/198 | Thundurus | swsh6-52 | holo`
- `057/198 | Gengar | swsh6-57 | holo`
- `061/198 | Gardevoir | swsh6-61 | holo`
- `064/198 | Cresselia | swsh6-64 | holo`
- `073/198 | Hatterene | swsh6-73 | holo`
- `083/198 | Galarian Runerigus | swsh6-83 | holo`
- `087/198 | Lycanroc | swsh6-87 | holo`
- `092/198 | Grapploct | swsh6-92 | holo`
- `098/198 | Galarian Slowking | swsh6-98 | holo`
- `108/198 | Single Strike Urshifu | swsh6-108 | holo`
- `114/198 | Cobalion | swsh6-114 | holo`
- `115/198 | Tauros | swsh6-115 | holo`
- `118/198 | Porygon-Z | swsh6-118 | holo`
- `123/198 | Shaymin | swsh6-123 | holo`
- `128/198 | Greedent | swsh6-128 | holo`

### regular v
- `007/198 | Celebi V | swsh6-7 | holo`
- `020/198 | Blaziken V | swsh6-20 | holo`
- `025/198 | Volcanion V | swsh6-25 | holo`
- `045/198 | Ice Rider Calyrex V | swsh6-45 | holo`
- `053/198 | Zeraora V | swsh6-53 | holo`
- `058/198 | Galarian Articuno V | swsh6-58 | holo`
- `074/198 | Shadow Rider Calyrex V | swsh6-74 | holo`
- `080/198 | Galarian Zapdos V | swsh6-80 | holo`
- `089/198 | Sandaconda V | swsh6-89 | holo`
- `097/198 | Galarian Moltres V | swsh6-97 | holo`
- `099/198 | Galarian Slowking V | swsh6-99 | holo`
- `104/198 | Liepard V | swsh6-104 | holo`
- `112/198 | Metagross V | swsh6-112 | holo`
- `119/198 | Blissey V | swsh6-119 | holo`
- `124/198 | Tornadus V | swsh6-124 | holo`

### regular vmax
- `008/198 | Celebi VMAX | swsh6-8 | holo`
- `021/198 | Blaziken VMAX | swsh6-21 | holo`
- `046/198 | Ice Rider Calyrex VMAX | swsh6-46 | holo`
- `075/198 | Shadow Rider Calyrex VMAX | swsh6-75 | holo`
- `090/198 | Sandaconda VMAX | swsh6-90 | holo`
- `100/198 | Galarian Slowking VMAX | swsh6-100 | holo`
- `113/198 | Metagross VMAX | swsh6-113 | holo`
- `125/198 | Tornadus VMAX | swsh6-125 | holo`

### full art v
- `160/198 | Celebi V (Full Art) | swsh6-160 | holo`
- `161/198 | Blaziken V (Full Art) | swsh6-161 | holo`
- `162/198 | Volcanion V (Full Art) | swsh6-162 | holo`
- `163/198 | Ice Rider Calyrex V (Full Art) | swsh6-163 | holo`
- `165/198 | Zeraora V (Full Art) | swsh6-165 | holo`
- `167/198 | Galarian Rapidash V (Full Art) | swsh6-167 | holo`
- `169/198 | Galarian Articuno V (Full Art) | swsh6-169 | holo`
- `171/198 | Shadow Rider Calyrex V (Full Art) | swsh6-171 | holo`
- `173/198 | Galarian Zapdos V (Full Art) | swsh6-173 | holo`
- `175/198 | Sandaconda V (Full Art) | swsh6-175 | holo`
- `176/198 | Galarian Moltres V (Full Art) | swsh6-176 | holo`
- `178/198 | Galarian Slowking V (Full Art) | swsh6-178 | holo`
- `180/198 | Liepard V (Full Art) | swsh6-180 | holo`
- `181/198 | Metagross V (Full Art) | swsh6-181 | holo`
- `182/198 | Blissey V (Full Art) | swsh6-182 | holo`
- `184/198 | Tornadus V (Full Art) | swsh6-184 | holo`

### full art trainer
- `186/198 | Agatha (Full Art) | swsh6-186 | holo`
- `187/198 | Avery (Full Art) | swsh6-187 | holo`
- `188/198 | Brawly (Full Art) | swsh6-188 | holo`
- `189/198 | Caitlin (Full Art) | swsh6-189 | holo`
- `190/198 | Doctor (Full Art) | swsh6-190 | holo`
- `191/198 | Flannery (Full Art) | swsh6-191 | holo`
- `192/198 | Honey (Full Art) | swsh6-192 | holo`
- `193/198 | Karen's Conviction (Full Art) | swsh6-193 | holo`
- `194/198 | Klara (Full Art) | swsh6-194 | holo`
- `195/198 | Melony (Full Art) | swsh6-195 | holo`
- `196/198 | Peonia (Full Art) | swsh6-196 | holo`
- `197/198 | Peony (Full Art) | swsh6-197 | holo`
- `198/198 | Siebold (Full Art) | swsh6-198 | holo`

### alternate art v
- `164/198 | Ice Rider Calyrex V (Alternate Full Art) | swsh6-164 | holo`
- `166/198 | Zeraora V (Alternate Full Art) | swsh6-166 | holo`
- `168/198 | Galarian Rapidash V (Alternate Full Art) | swsh6-168 | holo`
- `170/198 | Galarian Articuno V (Alternate Full Art) | swsh6-170 | holo`
- `172/198 | Shadow Rider Calyrex V (Alternate Full Art) | swsh6-172 | holo`
- `174/198 | Galarian Zapdos V (Alternate Full Art) | swsh6-174 | holo`
- `177/198 | Galarian Moltres V (Alternate Full Art) | swsh6-177 | holo`
- `179/198 | Galarian Slowking V (Alternate Full Art) | swsh6-179 | holo`
- `183/198 | Blissey V (Alternate Full Art) | swsh6-183 | holo`
- `185/198 | Tornadus V (Alternate Full Art) | swsh6-185 | holo`

### alternate art vmax
- `201/198 | Blaziken VMAX (Alternate Art Secret) | swsh6-201 | holo`
- `203/198 | Ice Rider Calyrex VMAX (Alternate Art Secret) | swsh6-203 | holo`
- `205/198 | Shadow Rider Calyrex VMAX (Alternate Art Secret) | swsh6-205 | holo`

### rainbow trainer
- `210/198 | Agatha (Secret) | swsh6-210 | holo`
- `211/198 | Avery (Secret) | swsh6-211 | holo`
- `212/198 | Brawly (Secret) | swsh6-212 | holo`
- `213/198 | Caitlin (Secret) | swsh6-213 | holo`
- `214/198 | Doctor (Secret) | swsh6-214 | holo`
- `215/198 | Flannery (Secret) | swsh6-215 | holo`
- `216/198 | Karen's Conviction (Secret) | swsh6-216 | holo`
- `217/198 | Klara (Secret) | swsh6-217 | holo`
- `218/198 | Melony (Secret) | swsh6-218 | holo`
- `219/198 | Peonia (Secret) | swsh6-219 | holo`
- `220/198 | Peony (Secret) | swsh6-220 | holo`
- `221/198 | Siebold (Secret) | swsh6-221 | holo`

### rainbow vmax
- `199/198 | Celebi VMAX (Secret) | swsh6-199 | holo`
- `200/198 | Blaziken VMAX (Secret) | swsh6-200 | holo`
- `202/198 | Ice Rider Calyrex VMAX (Secret) | swsh6-202 | holo`
- `204/198 | Shadow Rider Calyrex VMAX (Secret) | swsh6-204 | holo`
- `206/198 | Sandaconda VMAX (Secret) | swsh6-206 | holo`
- `207/198 | Galarian Slowking VMAX (Secret) | swsh6-207 | holo`
- `208/198 | Metagross VMAX (Secret) | swsh6-208 | holo`
- `209/198 | Tornadus VMAX (Secret) | swsh6-209 | holo`

### gold secret rare
- `222/198 | Electrode (Secret) | swsh6-222 | holo`
- `223/198 | Bronzong (Secret) | swsh6-223 | holo`
- `224/198 | Snorlax (Secret) | swsh6-224 | holo`
- `225/198 | Echoing Horn (Secret) | swsh6-225 | holo`
- `226/198 | Fan of Waves (Secret) | swsh6-226 | holo`
- `227/198 | Fog Crystal (Secret) | swsh6-227 | holo`
- `228/198 | Rugged Helmet (Secret) | swsh6-228 | holo`
- `229/198 | Urn of Vitality (Secret) | swsh6-229 | holo`
- `230/198 | Welcoming Lantern (Secret) | swsh6-230 | holo`
- `231/198 | Water Energy (Secret) | swsh6-231 | holo`
- `232/198 | Psychic Energy (Secret) | swsh6-232 | holo`
- `233/198 | Fighting Energy (Secret) | swsh6-233 | holo`

## Mapping Requirement Conclusion
A config-controlled outcome-to-pool mapping remains required for Chilling Reign rare-slot modeling because high-rarity buckets are not resolvable from structured subtype/special-type fields alone. Current resolution relies on card-number and card-name controlled rules.
