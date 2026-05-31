# Battle Styles Source and Bucket Audit Note

Date: 2026-05-30
Scope: swsh5 (Battle Styles) only

## Direct source verification

- Direct community thread: https://www.reddit.com/r/PokemonTCG/comments/mx0gvz/battle_styles_pull_data_after_almost_20000_packs/
- Thread title matches: "Battle Styles Pull Data (after almost 20.000 packs opened)"
- Relevant direct row used for modeling: Alt VMAX = 29 pulls over 19,837 packs (~1/684)
- Source type remains community sample evidence, not official Pokemon-published odds.

## ThePriceDex cross-reference handling

- Cross-reference page: https://www.thepricedex.com/set/swsh5/battle-styles/pull-rates
- ThePriceDex stays secondary/index-only metadata for swsh5.
- ThePriceDex labels are used for taxonomy cross-reference only:
  - Rare Holo VMAX maps to regular/base VMAX taxonomy context.
  - Secret Rare is broad and is not direct evidence for alternate art vmax.

## Taxonomy mapping audit

Reddit rows (direct community sample evidence):
- Alt VMAX -> alternate art vmax
- Alt -> alternate art v
- Rainbow -> rainbow rare (swsh5 broad runtime bucket)
- Full-Art -> full art (swsh5 broad runtime bucket)
- Gold -> gold rare

ThePriceDex rows (secondary index only):
- Rare Holo VMAX -> regular vmax (cross-reference only)
- Secret Rare -> broad secret-rare index label (not promoted to alternate art vmax)

Simulator runtime buckets (swsh5):
- rare
- holo rare
- regular v
- regular vmax
- full art
- rainbow rare
- gold rare
- alternate art v
- alternate art vmax

## Battle Styles card-row confirmation (read-only DB)

Confirmed alternate art vmax cards:
- bda9f1d8-2e8a-4efd-ab8c-194a2c12b80e | Single Strike Urshifu VMAX (Alternate Art Secret) | 168/163 | Secret Rare
- c6addb5e-5777-4d7b-ab6d-39266aa8cf0e | Rapid Strike Urshifu VMAX (Alternate Art Secret) | 170/163 | Secret Rare

Confirmed regular vmax cards (must remain non-alt):
- f6365f35-1cf4-41c6-9595-a82014ad00b4 | Single Strike Urshifu VMAX | 086/163 | Ultra Rare
- c3950d11-222a-42bf-b7af-2328fe042f82 | Rapid Strike Urshifu VMAX | 088/163 | Ultra Rare

Variant metadata observed for all listed cards:
- printing_type: holo
- special_type: null
- edition: null

## Modeling result summary

- Added explicit alternate art vmax runtime bucket for swsh5.
- Added explicit swsh5 mapping rule for "VMAX (Alternate Art Secret)" under Secret Rare.
- Added direct reference evidence row for Alt VMAX with odds_display 1/684.
- Updated swsh5 Reddit source URL from generic subreddit root to exact thread URL.
- Kept ThePriceDex evidence rows as SECONDARY_INDEX_ONLY.
