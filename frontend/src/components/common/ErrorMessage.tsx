import { AlertTriangle, RefreshCw } from 'lucide-react';
import { clsx } from 'clsx';

interface ErrorMessageProps {
  message: string;
  onRetry?: () => void;
  compact?: boolean;
  className?: string;
}

export default function ErrorMessage({
  message,
  onRetry,
  compact = false,
  className,
}: ErrorMessageProps) {
  if (compact) {
    return (
      <p className={clsx('flex items-center gap-1.5 text-sm text-red-400', className)}>
        <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
        {message}
      </p>
    );
  }

  return (
    <div
      className={clsx(
        'flex flex-col items-center justify-center gap-3 rounded-lg',
        'bg-red-950/30 border border-red-800/40 p-5 text-center',
        className,
      )}
      role="alert"
    >
      <AlertTriangle className="h-6 w-6 text-red-400 flex-shrink-0" />
      <p className="text-sm text-red-300">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-1.5 rounded-md bg-red-800/40 px-3 py-1.5
                     text-xs text-red-300 hover:bg-red-800/60 transition-colors"
        >
          <RefreshCw className="h-3 w-3" />
          Retry
        </button>
      )}
    </div>
  );
}
