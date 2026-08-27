export function eraStrengthRows(contract) {
  return (Array.isArray(contract?.eras) ? contract.eras : []).slice().sort((a, b) => {
    if (a?.rank == null) return b?.rank == null ? String(a?.eraName).localeCompare(String(b?.eraName)) : 1;
    if (b?.rank == null) return -1;
    return Number(a.rank) - Number(b.rank);
  });
}

export function displayScore(value) {
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toFixed(1)} / 10` : null;
}
