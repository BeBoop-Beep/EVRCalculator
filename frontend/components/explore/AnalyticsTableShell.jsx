"use client";

import InfoPopover from "@/components/ui/InfoPopover";
import TableSearchInput from "@/components/ui/TableSearchInput";
import styles from "./explore.module.css";

export default function AnalyticsTableShell({ title, info, query, onQueryChange, searchPlaceholder, searchLabel, context = null, shown, ranked = null, marketDate = null, children, className = "" }) {
  return <section className={`${styles.surface} ${styles.analyticsTableShell} min-w-0 overflow-hidden ${className}`} data-analytics-table-shell>
    <div className={`${styles.divider} ${styles.analyticsToolbar} grid gap-3 px-3 py-3 desk:py-2.5 sm:px-4 md:grid-cols-[minmax(0,1fr)_16rem_minmax(0,1fr)] md:items-center`}>
      <div className="flex min-w-0 items-center gap-1.5"><h2 className="truncate text-[18px] font-semibold leading-tight text-[var(--text-primary)] desk:text-[15px]">{title}</h2>{info ? <InfoPopover text={info} /> : null}</div>
      <TableSearchInput value={query} onChange={onQueryChange} placeholder={searchPlaceholder} ariaLabel={searchLabel} containerClassName="md:justify-self-center" />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--text-secondary)] md:justify-end md:text-right">
        {context ? <span className="hidden lg:inline">{context}</span> : null}
        <span className="whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.09em]"><span className="tabular-nums text-[var(--text-primary)]">{shown}</span> shown{ranked == null ? "" : <> · <span className="tabular-nums">{ranked}</span> ranked</>}</span>
        {marketDate ? <span className="whitespace-nowrap text-[11px] tabular-nums">As of {marketDate}</span> : null}
      </div>
    </div>
    {children}
  </section>;
}
