create or replace function public.market_explorer_filter_rarity_key(p_rarity text)
returns text
language sql
immutable
parallel safe
security invoker
set search_path to ''
as $function$
select case regexp_replace(lower(btrim(coalesce(p_rarity,''))), '[^a-z0-9]+', ' ', 'g')
  when 'ace spec rare' then 'aceSpecRare'
  when 'amazing rare' then 'amazingRare'
  when 'black white rare' then 'blackWhiteRare'
  when 'classic collection' then 'classicCollection'
  when 'common' then 'common'
  when 'double rare' then 'doubleRare'
  when 'holo rare' then 'holoRare'
  when 'hyper rare' then 'hyperRare'
  when 'illustration rare' then 'illustrationRare'
  when 'legend' then 'legend'
  when 'mega hyper rare' then 'megaHyperRare'
  when 'mega attack rare' then 'megaAttackRare'
  when 'promo' then 'promo'
  when 'radiant rare' then 'radiantRare'
  when 'rare' then 'rare'
  when 'rare ace' then 'rareAce'
  when 'rare break' then 'rareBreak'
  when 'rare holo' then 'rareHolo'
  when 'rare holo ex' then 'rareHoloEx'
  when 'rare holo gx' then 'rareHoloGx'
  when 'rare holo lv x' then 'rareHoloLvX'
  when 'rare holo star' then 'rareHoloStar'
  when 'rare holo v' then 'rareHoloV'
  when 'rare holo vmax' then 'rareHoloVmax'
  when 'rare holo vstar' then 'rareHoloVstar'
  when 'rare prime' then 'rarePrime'
  when 'rare prism star' then 'rarePrismStar'
  when 'rare rainbow' then 'rareRainbow'
  when 'rare secret' then 'rareSecret'
  when 'rare shining' then 'rareShining'
  when 'rare shiny' then 'rareShiny'
  when 'rare shiny gx' then 'rareShinyGx'
  when 'rare ultra' then 'rareUltra'
  when 'shiny rare' then 'shinyRare'
  when 'shiny ultra rare' then 'shinyUltraRare'
  when 'special illustration rare' then 'specialIllustrationRare'
  when 'trainer gallery rare holo' then 'trainerGalleryRareHolo'
  when 'ultra rare' then 'ultraRare'
  when 'uncommon' then 'uncommon'
  else null
end;
$function$;

comment on function public.market_explorer_filter_rarity_key(text) is
'Phase-3 exact Market Explorer card-rarity filter taxonomy. This is intentionally broader than market_explorer_rarity_segment(), which remains the prepared-market quality gate. NULL/unrecognized values are not assigned a filter ID.';

revoke all on function public.market_explorer_filter_rarity_key(text) from public, anon, authenticated;
grant execute on function public.market_explorer_filter_rarity_key(text) to service_role;
