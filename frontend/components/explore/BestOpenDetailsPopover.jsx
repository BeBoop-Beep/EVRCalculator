"use client";

import InfoPopover from "@/components/ui/InfoPopover";
import { bestOpenDetails } from "./productRankingsPresentation.mjs";

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const currency = (value) => Number.isFinite(value) ? money.format(value) : "Unavailable";

export default function BestOpenDetailsPopover({ row }) {
  const details = bestOpenDetails(row);
  return <span className="inline-flex items-center justify-end gap-1.5" data-best-open-cell>
    <strong className="text-[var(--text-primary)]">{details.available ? currency(details.threshold) : "—"}</strong>
    <InfoPopover ariaLabel={`Best-Open details for ${row?.productName || "this Product"}`}>
      <dl className="space-y-2">
        <div><dt className="font-semibold text-[var(--text-primary)]">Best-Open threshold</dt><dd className="tabular-nums">{currency(details.threshold)}</dd></div>
        <div><dt className="font-semibold text-[var(--text-primary)]">Current market</dt><dd className="tabular-nums">{currency(details.marketPrice)}</dd></div>
        {details.differenceText ? <div><dt className="font-semibold text-[var(--text-primary)]">Difference</dt><dd className="tabular-nums">{details.differenceText}</dd></div> : null}
        {details.interpretation ? <div><dt className="font-semibold text-[var(--text-primary)]">Interpretation</dt><dd>{details.interpretation}</dd></div> : null}
        <div><dt className="font-semibold text-[var(--text-primary)]">Evidence</dt><dd>Best-Open: {details.bestOpenDate || "date unavailable"}<br />Market: {details.marketDate || "date unavailable"}<br />Status: {details.status || "unavailable"}{details.freshness === "older" ? " · independently dated" : ""}</dd></div>
        <div><dt className="font-semibold text-[var(--text-primary)]">MSRP</dt><dd>Unavailable</dd></div>
      </dl>
    </InfoPopover>
  </span>;
}
