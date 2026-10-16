import { useEffect, useState } from 'react';
import { Timer } from 'lucide-react';
import { clsx } from 'clsx';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { getRequestStart } from '@/lib/requestStart';

interface TimedProgressProps {
  title: string;
  /** Query key of the request; elapsed time is measured from when it started. */
  requestKey?: readonly unknown[];
  /** How long the operation usually takes, in seconds. */
  typicalSeconds?: number;
  note?: string;
}

// For slow requests with no real progress signal: the bar is time-based,
// easing toward ~95% over the typical duration and never claiming completion.
export default function TimedProgress({
  title,
  requestKey,
  typicalSeconds = 30,
  note = 'You can explore the map meanwhile — results will appear here.',
}: TimedProgressProps) {
  const [mountedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, []);

  // Read on every tick: the request may start just after this mounts.
  const startedAt = (requestKey && getRequestStart(requestKey)) ?? mountedAt;
  const elapsed = Math.max(0, (now - startedAt) / 1000);

  const overdue = elapsed > typicalSeconds;
  const progress = overdue ? 95 : 95 * (1 - Math.pow(1 - elapsed / typicalSeconds, 2));
  const remaining = Math.max(0, Math.ceil(typicalSeconds - elapsed));

  return (
    <div className="flex flex-col items-center px-6 py-12 text-center" role="status" aria-live="polite">
      <LoadingSpinner size="lg" />

      <p className="mt-4 text-sm font-semibold text-slate-200">{title}</p>
      <p className="mt-1 flex items-center gap-1.5 text-xs text-slate-400">
        <Timer className="h-3.5 w-3.5" />
        This usually takes around {typicalSeconds} seconds
      </p>

      <div className="mt-5 h-1.5 w-full max-w-[240px] overflow-hidden rounded-full bg-slate-700/60">
        <div
          className={clsx(
            'h-full rounded-full bg-primary-500 transition-[width] duration-300 ease-linear',
            overdue && 'animate-pulse',
          )}
          style={{ width: `${progress}%` }}
        />
      </div>

      <p className="mt-2 font-mono text-[11px] text-slate-500">
        {overdue
          ? `${Math.floor(elapsed)}s — taking a little longer than usual, almost there…`
          : `${Math.floor(elapsed)}s elapsed · ~${remaining}s left`}
      </p>

      {note && <p className="mt-4 text-[11px] text-slate-500">{note}</p>}
    </div>
  );
}
