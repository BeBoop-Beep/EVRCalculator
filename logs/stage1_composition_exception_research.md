# Stage 1 composition exception research

Audit date: 2026-08-16

## Decision

The seven in-scope half booster boxes are verified as the definitionally uniform
18-pack retail format. They contain homogeneous booster packs from the named set
and no guaranteed card or other modeled-value component. They are represented as
`half_booster_box`, separate from the 36-pack `booster_box` family, because the
comparison contract permits only within-family comparisons of equivalent retail
formats.

The Prismatic Evolutions Sam's Club listing is `UNSUPPORTED_COMPOSITE_PRODUCT`.
It combines a six-pack Booster Bundle with a four-pack Surprise Box. The Surprise
Box also contains one of nine randomly selected logo promo cards, a storage box,
four dividers, and a code card. Stage 2 requires exact deterministic guaranteed
`card_variant_id` components and therefore cannot honestly represent the random
promo identity.

## Production half-box cohort

All prices below are each SKU's own latest positive TCGplayer observation on
2026-08-16. Each canonical calculation run had no exact pack-outcome artifact,
so every SKU is `WAITING_FOR_NEXT_ARTIFACT_BACKED_CANONICAL_RUN`.

| Set | sealed_product_id | Catalog product name | Price | Packs | Other modeled contents |
| --- | --- | --- | ---: | ---: | --- |
| Destined Rivals | `469913eb-c3eb-45af-9a20-61026faaa7e7` | Destined Rivals Half Booster Box | $296.00 | 18 | None |
| Mega Evolution | `37904746-f596-4385-94fd-8f042da87081` | Mega Evolution Half Booster Box | $250.00 | 18 | None |
| Paldea Evolved | `d1568fe7-273e-4c42-8c1b-e1cfe925745a` | Paldea Evolved Half Booster Box | $248.33 | 18 | None |
| Stellar Crown | `710c6435-6b65-4a97-ba83-a1a859538d3a` | Stellar Crown Half Booster Box | $228.33 | 18 | None |
| Surging Sparks | `0360d5da-eeeb-4787-912c-c6ef0d2206c6` | Surging Sparks Half Booster Box | $189.81 | 18 | None |
| Temporal Forces | `030d1c77-5109-4a5c-bc84-bb013ddc3d9c` | Temporal Forces Half Booster Box | $189.71 | 18 | None |
| Twilight Masquerade | `defd0a85-35b9-46b7-897d-32bf5e8ad35b` | Twilight Masqueade Half Booster Box | $194.86 | 18 | None |

Evolving Skies has a cataloged half box but is outside the supported canonical
set cohort for this task and was not changed.

## Evidence

- TCGplayer's Mega Evolution buyer's guide defines a half booster box as 18
  packs rather than the 36 in a full box and describes no additional contents:
  https://www.tcgplayer.com/content/article/Buyer-s-Guide-to-Pok%C3%A9mon-TCG-Mega-Evolution/7c1e123e-1c00-48f3-ae59-295d86a60933/
- TCGplayer's Destined Rivals buyer's guide calculates the half box at 18 packs:
  https://www.tcgplayer.com/content/article/Buyer-s-Guide-to-Pok%C3%A9mon-TCG-Destined-Rivals/bfa6befd-8bb9-4c3b-8684-2c5cd05fc4c8/
- TCGplayer's Surging Sparks catalog explicitly states 18 booster packs:
  https://www.tcgplayer.com/product/646039/pokemon-sv08-surging-sparks-surging-sparks-half-booster-box
- European product listings consistently specify the same 18-pack format for
  Stellar Crown, Paldea Evolved, Twilight Masquerade, and Temporal Forces:
  https://tcgmeta.co.uk/products/stellar-crown-half-booster-box-18-packs
  https://www.aplacards.co.uk/product-page/pok%C3%A9mon-paldea-evolved-half-booster-box-18-packs
  https://tcgmeta.co.uk/products/twilight-masquerade-half-booster-box-18-booster-packs
  https://www.diceanddestiny.co.uk/products/pokemon-temporal-forces-18-booster-box
- TCGplayer's exact Sam's Club catalog row lists both components, ten total
  packs, and the randomly selected one-of-nine Surprise Box promo:
  https://www.tcgplayer.com/product/678555/pokemon-sv-prismatic-evolutions-pokemon

## Production activation

Only the seven affected set-level sealed-market snapshots were rebuilt through
the normal targeted snapshot builder. Each now publishes
`sealed-product-classification-v2` and identifies the affected SKU as
`half_booster_box`. No simulation, score, ranking, or RIP-decision refresh was
run.
