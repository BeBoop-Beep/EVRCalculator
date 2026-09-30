export function retryFailedActivityPages(canonical, activity) {
  if (canonical.error) canonical.retry();
  if (activity.status === "error") activity.retry();
}
