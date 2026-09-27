-- Pack-energy identities participate in opening outcomes but are not part of the numbered collector checklist value.
update public.pokemon_canonical_cards pcc
set catalog_role='pack_energy',
    set_value_eligible=false,
    opening_eligible=true,
    eligibility_reason='booster_pack_energy_slot_not_collector_checklist',
    canonical_review_status='approved',
    updated_at=now()
from public.sets s
where pcc.set_id=s.id
  and (
    (s.canonical_key='sunAndMoon' and pcc.number ~ '^(16[4-9]|17[0-2])$')
    or pcc.catalog_role='pack_energy'
  );
