"use client";

function titleCaseLabel(value) {
  const label = String(value || "").trim();
  if (!label) {
    return "Unknown";
  }

  return label
    .replace(/[_-]/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function toFiniteNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatProbability(value) {
  const parsed = toFiniteNumber(value);
  if (parsed === null) {
    return "-";
  }
  return `${(parsed * 100).toFixed(parsed > 0 && parsed < 0.01 ? 3 : 2)}%`;
}

function compactList(values) {
  return (Array.isArray(values) ? values : []).filter(
    (value) => typeof value === "string" && value.trim()
  );
}

function formatSourceIds(sourceIds) {
  const values = compactList(sourceIds);
  return values.length > 0 ? values.join(", ") : "-";
}

function normalizeText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function hasMeaningfulLabel(row) {
  const sourceLabel = normalizeText(row?.source_bucket_label);
  if (!sourceLabel) {
    return false;
  }

  const normalizedBucket = normalizeText(row?.normalized_bucket).toLowerCase();
  return sourceLabel.toLowerCase() !== normalizedBucket;
}

function shouldShowEvidenceRow(row) {
  const probability = toFiniteNumber(row?.probability_used);
  const hasPositiveProbability = probability !== null && probability > 0;
  const hasSourceIds = compactList(row?.source_ids).length > 0;
  const hasLabel = hasMeaningfulLabel(row);
  const hasCaveat = Boolean(normalizeText(row?.caveat));
  const isRuntimeDisabled = row?.used_in_runtime === false;
  const isUnsupportedSplit = normalizeText(row?.source_status).toUpperCase() === "UNSUPPORTED_SPLIT";

  if (!hasPositiveProbability && !hasSourceIds && !hasLabel && !hasCaveat) {
    return false;
  }

  if ((isRuntimeDisabled || isUnsupportedSplit) && !hasSourceIds && !hasCaveat) {
    return false;
  }

  return true;
}

function getEvidenceNote(row) {
  const explicitCaveat = normalizeText(row?.caveat);
  if (explicitCaveat) {
    return explicitCaveat;
  }

  const status = normalizeText(row?.source_status).toUpperCase();
  if (status === "PROVISIONAL_DIRECTIONAL") {
    return "Provisional directional estimate.";
  }
  if (status === "SOURCE_DERIVED_RESIDUAL") {
    return "Derived from remaining modeled probability mass.";
  }

  return null;
}

function getExternalSourceUrl(source) {
  const url = normalizeText(source?.source_url);
  return /^https?:\/\//i.test(url) ? url : null;
}

function SummaryPill({ label, value, muted = false }) {
  if (!value) {
    return null;
  }

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs ${
        muted
          ? "border-[var(--border-subtle)] bg-[var(--surface-page)]/40 text-[var(--text-secondary)]"
          : "border-[var(--border-subtle)] bg-[var(--surface-page)]/55 text-[var(--text-primary)]"
      }`}
    >
      <span className="font-semibold uppercase tracking-[0.06em] text-[var(--text-secondary)]">{label}:</span>
      <span className="ml-1">{value}</span>
    </span>
  );
}

function SourceCard({ source }) {
  const sourceUrl = getExternalSourceUrl(source);

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm font-semibold text-[var(--text-primary)]">{source.source_name || "Unnamed source"}</p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {titleCaseLabel(source.source_type)}
            {source.source_confidence ? ` • ${titleCaseLabel(source.source_confidence)} confidence` : ""}
          </p>
        </div>
        {sourceUrl ? (
          <a
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
            className="text-xs font-medium text-[var(--accent)] underline decoration-[color:var(--accent)]/50 underline-offset-2 hover:text-[var(--text-primary)]"
          >
            Open source
          </a>
        ) : (
          <span className="text-xs text-[var(--text-tertiary,var(--text-secondary))]">URL unavailable</span>
        )}
      </div>
      {source.discovered_via ? (
        <p className="mt-2 text-xs text-[var(--text-secondary)]">
          <span className="font-semibold uppercase tracking-[0.06em]">Discovered via:</span> {source.discovered_via}
        </p>
      ) : null}
      {source.notes ? <p className="mt-2 text-xs leading-relaxed text-[var(--text-secondary)]">{source.notes}</p> : null}
    </div>
  );
}

function BucketEvidenceTable({ rows }) {
  return (
    <div className="hidden overflow-x-auto rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 md:block">
      <table className="w-full min-w-full divide-y divide-[var(--border-subtle)] text-left">
        <thead className="bg-[var(--surface-page)]/70">
          <tr>
            <th className="px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Bucket</th>
            <th className="px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Source Label</th>
            <th className="px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Odds / Probability</th>
            <th className="px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Source / Source IDs</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border-subtle)]">
          {rows.map((row) => (
            <tr key={`${row.normalized_bucket}:${row.source_bucket_label}:${row.source_status}`}>
              <td className="px-3 py-2 align-top text-sm text-[var(--text-primary)]">{titleCaseLabel(row.normalized_bucket)}</td>
              <td className="px-3 py-2 align-top text-sm text-[var(--text-secondary)]">{row.source_bucket_label || "-"}</td>
              <td className="px-3 py-2 align-top text-sm text-[var(--text-secondary)]">
                <div>{row.odds_display || formatProbability(row.probability_used)}</div>
                {!row.odds_display && row.probability_used != null ? (
                  <div className="mt-1 text-xs text-[var(--text-tertiary,var(--text-secondary))]">{formatProbability(row.probability_used)}</div>
                ) : null}
              </td>
              <td className="px-3 py-2 align-top text-sm text-[var(--text-secondary)]">
                <div>{formatSourceIds(row.source_ids)}</div>
                {getEvidenceNote(row) ? (
                  <div className="mt-1 text-xs leading-relaxed text-[var(--text-tertiary,var(--text-secondary))]">{getEvidenceNote(row)}</div>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BucketEvidenceMobile({ rows }) {
  return (
    <div className="space-y-2 md:hidden">
      {rows.map((row) => (
        <div
          key={`${row.normalized_bucket}:${row.source_bucket_label}:${row.source_status}:mobile`}
          className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/45 p-3"
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="text-sm font-semibold text-[var(--text-primary)]">{titleCaseLabel(row.normalized_bucket)}</p>
          </div>
          <div className="mt-2 space-y-1.5 text-xs text-[var(--text-secondary)]">
            <p><span className="font-semibold uppercase tracking-[0.06em]">Source Label:</span> {row.source_bucket_label || "-"}</p>
            <p><span className="font-semibold uppercase tracking-[0.06em]">Odds / Probability:</span> {row.odds_display || formatProbability(row.probability_used)}</p>
            <p><span className="font-semibold uppercase tracking-[0.06em]">Source / Source IDs:</span> {formatSourceIds(row.source_ids)}</p>
            {getEvidenceNote(row) ? <p className="leading-relaxed text-[var(--text-tertiary,var(--text-secondary))]">{getEvidenceNote(row)}</p> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function PullRateReferencesCard({ pullRateReferences }) {
  const references = pullRateReferences && typeof pullRateReferences === "object" ? pullRateReferences : null;
  if (!references) {
    return null;
  }

  const caveats = compactList(references.caveats);
  const sources = Array.isArray(references.sources) ? references.sources.filter(Boolean) : [];
  const bucketEvidence = Array.isArray(references.bucket_evidence)
    ? references.bucket_evidence.filter((row) => row && typeof row === "object")
    : [];
  const visibleBucketEvidence = bucketEvidence.filter(shouldShowEvidenceRow);

  return (
    <details className="group rounded-2xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/30 p-4 sm:p-5">
      <summary className="flex cursor-pointer list-none items-start justify-between gap-3 text-left transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--accent)]/70">
        <div>
          <p className="text-base font-semibold text-[var(--text-primary)]">References & Model Evidence</p>
          <p className="mt-0.5 text-sm text-[var(--text-secondary)]">View source evidence and model caveats.</p>
        </div>

        <div className="flex items-center gap-2">
          <SummaryPill label="Confidence" value={references.model_confidence ? titleCaseLabel(references.model_confidence) : null} />
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            className="h-5 w-5 flex-none text-[var(--text-secondary)] transition-transform duration-150 group-open:rotate-180"
            fill="currentColor"
          >
            <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
          </svg>
        </div>
      </summary>

      <div className="mt-4 space-y-3">
        <p className="text-sm text-[var(--text-secondary)]">
          Provisional evidence is directional and not official Pokemon odds.
        </p>

        <div className="flex flex-wrap gap-2">
          <SummaryPill label="Model Status" value={references.model_status ? titleCaseLabel(references.model_status) : null} />
          <SummaryPill label="Last Reviewed" value={references.last_reviewed_at || null} muted />
        </div>

        {caveats.length > 0 ? (
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 px-3 py-2.5">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Caveats</p>
            <div className="mt-1.5 space-y-1">
              {caveats.map((caveat) => (
                <p key={caveat} className="text-sm leading-relaxed text-[var(--text-secondary)]">{caveat}</p>
              ))}
            </div>
          </div>
        ) : null}

        {sources.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.08em] text-[var(--text-secondary)]">Sources</p>
            <div className="grid gap-2 lg:grid-cols-2">
              {sources.map((source) => (
                <SourceCard key={source.source_id || source.source_name} source={source} />
              ))}
            </div>
          </div>
        ) : null}

        {visibleBucketEvidence.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs text-[var(--text-secondary)]">
              Bucket-level evidence is available for advanced review.
            </p>
            <details className="group rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)]/35 px-3 py-2.5">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-left text-sm font-medium text-[var(--text-primary)] transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--accent)]/70">
                <span>Show bucket-level evidence</span>
                <svg
                  aria-hidden="true"
                  viewBox="0 0 20 20"
                  className="h-4 w-4 flex-none text-[var(--text-secondary)] transition-transform duration-150 group-open:rotate-180"
                  fill="currentColor"
                >
                  <path d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.12l3.71-3.89a.75.75 0 1 1 1.08 1.04l-4.25 4.45a.75.75 0 0 1-1.08 0L5.21 8.27a.75.75 0 0 1 .02-1.06Z" />
                </svg>
              </summary>
              <div className="mt-3 space-y-2">
                <p className="text-xs text-[var(--text-secondary)]">
                  Bucket-level evidence shows how each modeled pull bucket maps back to the sources used by the simulator.
                </p>
                <BucketEvidenceTable rows={visibleBucketEvidence} />
                <BucketEvidenceMobile rows={visibleBucketEvidence} />
              </div>
            </details>
          </div>
        ) : null}
      </div>
    </details>
  );
}