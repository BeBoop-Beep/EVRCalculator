const TABS = [
  ["overview", "RIP"],
  ["market", "Market"],
  ["cards", "Cards & Products"],
  ["pull-rates", "Pull Rates"],
];

export default function SetRuntimeTabs({ activeTab, onSelect, onCardsIntent }) {
  return (
    <nav aria-label="Set sections" className="flex gap-1 overflow-x-auto border-t border-[var(--border-subtle)] px-3 py-2 sm:px-5">
      {TABS.map(([tab, label]) => (
        <button
          key={tab}
          type="button"
          onClick={() => onSelect(tab)}
          onMouseEnter={tab === "cards" ? onCardsIntent : undefined}
          onFocus={tab === "cards" ? onCardsIntent : undefined}
          aria-current={activeTab === tab ? "page" : undefined}
          className={`shrink-0 rounded-lg px-3 py-2 text-sm font-semibold transition-colors ${activeTab === tab ? "bg-[var(--surface-hover)] text-[var(--text-primary)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}
        >
          {label}
        </button>
      ))}
    </nav>
  );
}
