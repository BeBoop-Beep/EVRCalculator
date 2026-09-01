const numberOrNull = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};

export function selectSetRichSharedViewModel({ setId, target, shell, ripBootstrap } = {}) {
  const shellSet = shell?.set || shell || null;
  const shellId = shellSet?.id || shellSet?.setId || null;
  const targetId = target?.id || target?.setId || null;
  const identityMatches = !setId || ((!shellId || shellId === setId) && (!targetId || targetId === setId));
  if (!identityMatches) return { identity: { setId: setId || null, valid: false }, cardCount: null, publication: null };
  // Preserve the pre-extraction cold-page semantics without instantiating the
  // paginated Cards resource. Shell identity counts can describe a different
  // population than the priced/checklist count shown by Set Market.
  const cardCount = numberOrNull(
    target?.card_count ??
      target?.cardCount ??
      target?.checklist_set_value_total_card_count ??
      target?.checklistSetValueTotalCardCount ??
      target?.simulated_set_value_card_count ??
      target?.simulatedSetValueCardCount ??
      shell?.summary?.simulated_set_value_card_count ??
      shell?.summary?.simulatedSetValueCardCount ??
      ripBootstrap?.summary?.simulated_set_value_card_count ??
      ripBootstrap?.summary?.simulatedSetValueCardCount
  );
  return {
    identity: { setId: setId || shellId || targetId || null, valid: true },
    cardCount,
    publication: { calculationRunId: ripBootstrap?.calculationRunId || ripBootstrap?.calculation_run_id || null, marketAsOfDate: shell?.setValueSummary?.asOf || shell?.meta?.marketAsOfDate || null },
  };
}
