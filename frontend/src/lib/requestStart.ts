// Remembers when a slow request actually started, keyed by its query key, so a
// loading UI can show real elapsed time even if it mounts after the request
// began (e.g. the map fires the analog search) or remounts on a tab switch.
const starts = new Map<string, number>();

const toId = (key: readonly unknown[]) => JSON.stringify(key);

export function getRequestStart(key: readonly unknown[]): number | undefined {
  return starts.get(toId(key));
}

export function clearRequestStart(key: readonly unknown[]): void {
  starts.delete(toId(key));
}

/**
 * Wraps a queryFn. The start time is kept on failure so React Query's automatic
 * retry continues the same timer; callers clear it before a manual retry.
 */
export async function trackRequest<T>(key: readonly unknown[], fn: () => Promise<T>): Promise<T> {
  const id = toId(key);
  if (!starts.has(id)) starts.set(id, Date.now());
  const result = await fn();
  starts.delete(id);
  return result;
}
