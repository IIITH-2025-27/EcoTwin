import { clsx } from 'clsx';
import type { TrendDirection } from '@/types';

type Variant =
  | 'default'
  | 'success'
  | 'warning'
  | 'danger'
  | 'info'
  | 'increasing'
  | 'declining'
  | 'stable';

interface BadgeProps {
  label: string;
  variant?: Variant;
  className?: string;
  dot?: boolean;
}

const variantStyles: Record<Variant, string> = {
  default: 'bg-slate-700/60 text-slate-300',
  success: 'bg-emerald-500/20 text-emerald-400 border border-emerald-600/30',
  warning: 'bg-amber-500/20 text-amber-400 border border-amber-600/30',
  danger: 'bg-red-500/20 text-red-400 border border-red-600/30',
  info: 'bg-blue-500/20 text-blue-400 border border-blue-600/30',
  increasing: 'bg-emerald-500/20 text-emerald-400 border border-emerald-600/30',
  declining: 'bg-red-500/20 text-red-400 border border-red-600/30',
  stable: 'bg-slate-500/20 text-slate-300 border border-slate-600/30',
};

const dotColors: Record<Variant, string> = {
  default: 'bg-slate-400',
  success: 'bg-emerald-400',
  warning: 'bg-amber-400',
  danger: 'bg-red-400',
  info: 'bg-blue-400',
  increasing: 'bg-emerald-400',
  declining: 'bg-red-400',
  stable: 'bg-slate-400',
};

export default function Badge({
  label,
  variant = 'default',
  className,
  dot = false,
}: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
        variantStyles[variant],
        className,
      )}
    >
      {dot && (
        <span
          className={clsx('h-1.5 w-1.5 rounded-full', dotColors[variant])}
        />
      )}
      {label}
    </span>
  );
}

/** Convenience: map a TrendDirection → Badge variant */
export function trendToBadgeVariant(trend: TrendDirection): Variant {
  return trend === 'increasing'
    ? 'increasing'
    : trend === 'declining'
    ? 'declining'
    : 'stable';
}
