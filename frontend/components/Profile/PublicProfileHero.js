import RouteTabsNav from "@/components/Profile/RouteTabsNav";

export default function PublicProfileHero({ identity, avatarUrl }) {
  const profileBaseHref = identity.profileHref;
  const subtitle = identity.subtitle || identity.secondaryHandle;
  const publicTabs = [
    { label: "Overview", href: profileBaseHref, exact: true },
    { label: "Collection", href: `${profileBaseHref}/collection` },
    { label: "Binder", href: `${profileBaseHref}/binder` },
    { label: "Shelf", href: `${profileBaseHref}/shelf` },
    { label: "Wishlist", href: `${profileBaseHref}/wishlist` },
    { label: "Activity", href: `${profileBaseHref}/activity` },
  ];

  return (
    <section className="page-hero-panel rounded-2xl px-6 py-8 sm:px-8">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--text-secondary)]">Public Showcase</p>

      <div className="mt-4 flex items-start gap-4">
        <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-full border border-[var(--border-subtle)] bg-brand text-xl font-semibold text-white shadow-[0_0_0_2px_rgba(255,255,255,0.08)] sm:h-20 sm:w-20 sm:text-2xl">
          {avatarUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={avatarUrl} alt={`${identity.username} avatar`} className="h-full w-full object-cover" />
          ) : (
            identity.avatarText
          )}
        </div>

        <div className="min-w-0">
          <h1 className="text-[28px] font-bold leading-tight text-[var(--text-primary)]">{identity.title}</h1>
          {subtitle ? <p className="mt-1 text-sm text-[var(--text-secondary)]">{subtitle}</p> : null}
                 <p className="mt-2 text-sm text-[var(--text-secondary)]">Collection highlights, portfolio visibility, and shared collector identity.</p>
        </div>
      </div>

      <RouteTabsNav items={publicTabs} ariaLabel="Public profile sections" />
    </section>
  );
}
