import Link from "next/link";
import PublicOverviewSection from "@/components/Profile/PublicOverviewSection";

export default function PublicRecentActivityPreview({ activities = [], username }) {
  const activityHref = `/u/${username}/activity`;

  return (
    <PublicOverviewSection
      title="Recent Activity"
      subtitle="Latest public updates from this collector."
      action={
        <Link href={activityHref} className="text-sm font-medium text-brand hover:text-brand/80">
          View activity
        </Link>
      }
    >
      {activities.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] p-8 text-sm text-[var(--text-secondary)]">
          No recent activity has been shared.
        </div>
      ) : (
        <div className="space-y-3">
          {activities.slice(0, 4).map((activity) => (
            <div
              key={activity.id}
              className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] px-4 py-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="text-sm font-semibold text-[var(--text-primary)]">{activity.title}</p>
                <p className="text-xs text-[var(--text-secondary)]">{activity.timestampLabel}</p>
              </div>
              <p className="mt-1 text-xs text-[var(--text-secondary)]">{activity.description}</p>
            </div>
          ))}
        </div>
      )}
    </PublicOverviewSection>
  );
}
