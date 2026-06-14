import { clsx } from 'clsx';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
  className?: string;
}

const sizeMap = {
  sm: 'h-4 w-4 border-2',
  md: 'h-6 w-6 border-2',
  lg: 'h-10 w-10 border-[3px]',
};

export default function LoadingSpinner({
  size = 'md',
  label,
  className,
}: LoadingSpinnerProps) {
  return (
    <div
      className={clsx('flex flex-col items-center justify-center gap-3', className)}
      role="status"
      aria-label={label ?? 'Loading…'}
    >
      <div
        className={clsx(
          'animate-spin rounded-full border-primary-500 border-t-transparent',
          sizeMap[size],
        )}
      />
      {label && (
        <span className="text-xs text-slate-400 animate-pulse">{label}</span>
      )}
    </div>
  );
}
