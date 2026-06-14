import { clsx } from 'clsx';
import type { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  noPadding?: boolean;
}

export default function Card({
  children,
  className,
  title,
  subtitle,
  action,
  noPadding = false,
}: CardProps) {
  return (
    <div
      className={clsx(
        'rounded-xl bg-surface-800 border border-slate-700/60 shadow-lg',
        className,
      )}
    >
      {(title || action) && (
        <div className="flex items-start justify-between border-b border-slate-700/40 px-4 py-3">
          <div>
            {title && (
              <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
            )}
            {subtitle && (
              <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>
            )}
          </div>
          {action && <div className="ml-2 flex-shrink-0">{action}</div>}
        </div>
      )}
      <div className={clsx(!noPadding && 'p-4')}>{children}</div>
    </div>
  );
}
