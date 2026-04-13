/**
 * Component for displaying a full activity timeline of collector actions.
 * Shows activity with type-specific icons, timestamps, and detailed descriptions.
 */
export default function PublicActivityTimeline({
  activities = [],
  emptyMessage = "No activity to display.",
  isLoading = false,
  className = "",
}) {
  if (isLoading) {
    return (
      <div className={`space-y-3 ${className}`}>
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="h-20 animate-pulse rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-hover)]"
          />
        ))}
      </div>
    );
  }

  if (!activities || activities.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--surface-page)] p-12 text-center">
        <p className="text-sm text-[var(--text-secondary)]">{emptyMessage}</p>
      </div>
    );
  }

  return (
    <div className={`space-y-3 ${className}`}>
      {activities.map((activity, idx) => (
        <ActivityCard
          key={activity.id || idx}
          activity={activity}
          isFirst={idx === 0}
        />
      ))}
    </div>
  );
}

function ActivityCard({ activity, isFirst = false }) {
  const typeConfig = getActivityTypeConfig(activity.type);

  return (
    <article className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4 transition-colors hover:border-[var(--border-prominent)]">
      <div className="flex gap-4">
        {/* Icon/Avatar */}
        <div className={`mt-0.5 h-10 w-10 shrink-0 rounded-full flex items-center justify-center text-lg ${typeConfig.bgColor}`}>
          {typeConfig.icon}
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <h3 className="text-sm font-semibold text-[var(--text-primary)]">{activity.title}</h3>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">{activity.description}</p>
            </div>
            <span className="shrink-0 whitespace-nowrap text-xs font-medium text-[var(--text-secondary)]">
              {activity.timestampLabel || "Recently"}
            </span>
          </div>

          {/* Additional Details */}
          {activity.details && (
            <div className="mt-3 space-y-1 rounded-lg bg-[var(--surface-hover)] p-2">
              {Array.isArray(activity.details) ? (
                activity.details.map((detail, idx) => (
                  <p
                    key={idx}
                    className="text-xs text-[var(--text-secondary)]"
                  >
                    <span className="font-medium text-[var(--text-primary)]">{detail.label}:</span> {detail.value}
                  </p>
                ))
              ) : (
                <p className="text-xs text-[var(--text-secondary)]">{activity.details}</p>
              )}
            </div>
          )}

          {/* Action Link */}
          {activity.actionLabel && (
            <a
              href={activity.actionHref || "#"}
              className="mt-3 inline-block text-xs font-medium text-brand hover:text-brand/80"
            >
              {activity.actionLabel} →
            </a>
          )}
        </div>
      </div>
    </article>
  );
}

function getActivityTypeConfig(type) {
  const configs = {
    added: {
      icon: "➕",
      bgColor: "bg-green-500/20 text-green-600",
      label: "Added",
    },
    graded: {
      icon: "🏆",
      bgColor: "bg-amber-500/20 text-amber-600",
      label: "Graded",
    },
    valued: {
      icon: "💎",
      bgColor: "bg-blue-500/20 text-blue-600",
      label: "Valued",
    },
    sold: {
      icon: "🔄",
      bgColor: "bg-purple-500/20 text-purple-600",
      label: "Sold",
    },
    wishlist: {
      icon: "⭐",
      bgColor: "bg-yellow-500/20 text-yellow-600",
      label: "Wishlist",
    },
    featured: {
      icon: "✨",
      bgColor: "bg-pink-500/20 text-pink-600",
      label: "Featured",
    },
    updated: {
      icon: "🔄",
      bgColor: "bg-gray-500/20 text-gray-600",
      label: "Updated",
    },
  };

  return configs[type] || configs.updated;
}
