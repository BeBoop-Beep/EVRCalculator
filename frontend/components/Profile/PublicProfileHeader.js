export default function PublicProfileHeader({
  identity,
  avatarUrl,
  bio,
  favoriteTcg,
  joinDateLabel,
  visibility,
}) {
  const subtitle = identity.subtitle || identity.handle;

  return (
    <section className="page-hero-panel overflow-hidden rounded-2xl p-4 sm:p-8">
      <div className="grid gap-4 sm:gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
        <div className="flex items-start gap-4 sm:gap-5">
          <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-full border border-[var(--border-subtle)] bg-brand text-xl font-semibold text-white shadow-[0_0_0_2px_rgba(255,255,255,0.06)] sm:h-20 sm:w-20 sm:text-2xl">
            {avatarUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={avatarUrl} alt={`${identity.username} avatar`} className="h-full w-full object-cover" />
            ) : (
              identity.avatarText
            )}
          </div>

          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--text-secondary)]">Collector Showcase</p>
            <h1 className="mt-2 text-3xl font-bold leading-tight text-[var(--text-primary)] sm:text-4xl">{identity.title}</h1>
            <p className="mt-1 text-sm text-[var(--text-secondary)]">{subtitle}</p>
            <p className="mt-2 sm:mt-3 max-w-2xl text-sm leading-relaxed text-[var(--text-secondary)]">{bio}</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5 sm:grid sm:gap-2 sm:grid-cols-3 lg:w-[28rem]">
          <MetaPill label="Favorite TCG" shortLabel="TCG" value={favoriteTcg} />
          <MetaPill label="Joined" shortLabel="Joined" value={joinDateLabel} />
          <MetaPill label="Visibility" shortLabel="Visibility" value={visibility} />
        </div>
      </div>
    </section>
  );
}

function MetaPill({ label, shortLabel, value }) {
  return (
    <div className="inline-flex min-w-0 items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[rgba(255,255,255,0.02)] px-2.5 py-1.5 sm:block sm:rounded-xl sm:px-3 sm:py-2">
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--text-secondary)] sm:hidden">{shortLabel}</p>
      <p className="hidden text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)] sm:block">{label}</p>
      <p className="truncate text-xs font-medium text-[var(--text-primary)] sm:mt-1 sm:text-sm">{value}</p>
    </div>
  );
}
