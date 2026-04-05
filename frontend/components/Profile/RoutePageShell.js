export default function RoutePageShell({ eyebrow, title, subtitle, children, trailing }) {
  return (
    <section className="dashboard-panel rounded-2xl p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          {eyebrow ? (
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">{eyebrow}</p>
          ) : null}
          <h1 className="mt-1 text-2xl font-semibold text-[var(--text-primary)]">{title}</h1>
          {subtitle ? <p className="mt-2 text-sm text-[var(--text-secondary)]">{subtitle}</p> : null}
        </div>
        {trailing ? <div>{trailing}</div> : null}
      </div>
      <div className="mt-6">{children}</div>
    </section>
  );
}
