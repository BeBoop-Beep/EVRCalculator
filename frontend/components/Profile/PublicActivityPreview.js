"use client";

import ProfileSection from "@/components/Profile/ProfileSection";
import Link from "next/link";

/**
 * @typedef {Object} ActivityItem
 * @property {string} id
 * @property {string} type - "added" | "graded" | "valued" | "updated"
 * @property {string} title
 * @property {string} description
 * @property {Date | string} timestamp
 * @property {string} [icon]
 */

/**
 * PublicActivityPreview - Shows recent activity and updates to the collection.
 * @param {Object} props
 * @param {ActivityItem[]} [props.activities] - Activity list
 * @param {string} [props.userUsername] - Username for link to full activity
 * @param {boolean} [props.isLoading] - Loading state
 * @returns {JSX.Element}
 */
export default function PublicActivityPreview({ activities = [], userUsername, isLoading = false }) {
  // Mock data for demonstration
  const mockActivities = [
    {
      id: "1",
      type: "added",
      icon: "➕",
      title: "Added Charizard ex",
      description: "Scarlet & Violet #123 • PSA 9",
      timestamp: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000),
    },
    {
      id: "2",
      type: "graded",
      icon: "📊",
      title: "Grading Received",
      description: "Mewtwo ex graded PSA 8",
      timestamp: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000),
    },
    {
      id: "3",
      type: "valued",
      icon: "💰",
      title: "Collection Valued",
      description: "Portfolio value updated to $4,740",
      timestamp: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000),
    },
    {
      id: "4",
      type: "updated",
      icon: "🔄",
      title: "Profile Updated",
      description: "Display name changed to 'Collector Prime'",
      timestamp: new Date(Date.now() - 14 * 24 * 60 * 60 * 1000),
    },
  ];

  const displayActivities = activities.length > 0 ? activities : mockActivities;

  const formatTimestamp = (ts) => {
    const date = ts instanceof Date ? ts : new Date(ts);
    const now = new Date();
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays} days ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
    return `${Math.floor(diffDays / 30)} months ago`;
  };

  const getActivityColor = (type) => {
    switch (type) {
      case "added":
        return "bg-emerald-500/10 text-emerald-500";
      case "graded":
        return "bg-blue-500/10 text-blue-500";
      case "valued":
        return "bg-purple-500/10 text-purple-500";
      case "updated":
        return "bg-gray-500/10 text-gray-500";
      default:
        return "bg-gray-500/10 text-gray-500";
    }
  };

  if (isLoading) {
    return (
      <ProfileSection title="Recent Activity" subtitle="Latest collection updates">
        <div className="space-y-3">
          {[1, 2, 3, 4].map((idx) => (
            <div key={idx} className="animate-pulse">
              <div className="h-20 rounded-lg bg-[var(--surface-hover)]" />
            </div>
          ))}
        </div>
      </ProfileSection>
    );
  }

  const activityLink = userUsername ? `/u/${userUsername}/activity` : "#";

  return (
    <ProfileSection
      title="Recent Activity"
      subtitle="Latest collection updates"
      actions={
        userUsername && (
          <Link href={activityLink} className="text-sm font-medium text-brand hover:text-brand/80 transition-colors">
            View All →
          </Link>
        )
      }
    >
      {displayActivities.length === 0 ? (
        <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-8 text-center">
          <p className="text-sm text-[var(--text-secondary)]">No activity yet.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {displayActivities.slice(0, 4).map((activity) => (
            <div
              key={activity.id}
              className="flex gap-4 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-page)] p-4 transition-colors hover:bg-[var(--surface-hover)]"
            >
              {/* Icon */}
              <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-lg ${getActivityColor(activity.type)}`}>
                {activity.icon || "📝"}
              </div>

              {/* Content */}
              <div className="min-w-0 flex-1">
                <h4 className="font-semibold text-[var(--text-primary)] text-sm">{activity.title}</h4>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)] line-clamp-1">{activity.description}</p>
              </div>

              {/* Timestamp */}
              <div className="shrink-0 text-right">
                <p className="text-xs font-medium text-[var(--text-secondary)]">
                  {formatTimestamp(activity.timestamp)}
                </p>
              </div>
            </div>
          ))}

          {displayActivities.length > 4 && (
            <div className="pt-2">
              <Link
                href={activityLink}
                className="inline-block text-sm font-medium text-brand hover:text-brand/80 transition-colors"
              >
                View all activity →
              </Link>
            </div>
          )}
        </div>
      )}
    </ProfileSection>
  );
}
