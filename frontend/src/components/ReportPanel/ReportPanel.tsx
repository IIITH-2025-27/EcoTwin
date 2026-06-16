import { useState } from 'react';
import {
  FileText,
  Download,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  RefreshCw,
} from 'lucide-react';
import { clsx } from 'clsx';
import Card from '@/components/common/Card';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import ErrorMessage from '@/components/common/ErrorMessage';
import { useReport } from '@/hooks/useReport';
import { useMapStore } from '@/store/mapStore';
import type { ReportStatus } from '@/types';

const STATUS_CONFIG: Record<
  ReportStatus,
  { label: string; color: string; icon: React.ReactNode }
> = {
  pending: {
    label: 'Pending',
    color: 'text-amber-400',
    icon: <Clock className="h-4 w-4" />,
  },
  processing: {
    label: 'Generating…',
    color: 'text-blue-400',
    icon: <Loader2 className="h-4 w-4 animate-spin" />,
  },
  completed: {
    label: 'Ready',
    color: 'text-emerald-400',
    icon: <CheckCircle className="h-4 w-4" />,
  },
  failed: {
    label: 'Failed',
    color: 'text-red-400',
    icon: <XCircle className="h-4 w-4" />,
  },
};

export default function ReportPanel() {
  const { selectedRegionId } = useMapStore();
  const { report, pollError, generate, isGenerating, generateError, reset } =
    useReport();

  const [includesForecast, setIncludesForecast] = useState(true);
  const [includesAnalogs, setIncludesAnalogs] = useState(true);
  const [topKAnalogs, setTopKAnalogs] = useState(5);

  if (!selectedRegionId) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-12 text-center px-4">
        <FileText className="h-10 w-10 text-slate-700" />
        <p className="text-sm text-slate-400">Select a region to generate a report</p>
      </div>
    );
  }

  const handleGenerate = () => {
    generate({
      region_id: selectedRegionId,
      include_forecast: includesForecast,
      include_analogs: includesAnalogs,
      top_k_analogs: topKAnalogs,
    });
  };

  const isActive = !!report;
  const currentStatus = report?.status;
  const statusConf = currentStatus ? STATUS_CONFIG[currentStatus] : null;

  return (
    <div className="space-y-3 p-3 tab-content-enter">
      {/* Options */}
      <Card title="Report Options">
        <div className="space-y-3">
          {/* Toggles */}
          {[
            {
              id: 'forecast',
              label: 'Include Forecast',
              desc: '5-year analog-based projection',
              checked: includesForecast,
              onChange: setIncludesForecast,
            },
            {
              id: 'analogs',
              label: 'Include Analogs',
              desc: 'Top-K similar ecosystem regions',
              checked: includesAnalogs,
              onChange: setIncludesAnalogs,
            },
          ].map(({ id, label, desc, checked, onChange }) => (
            <label
              key={id}
              className="flex cursor-pointer items-start justify-between gap-3"
            >
              <div>
                <p className="text-sm text-slate-200">{label}</p>
                <p className="text-xs text-slate-500">{desc}</p>
              </div>
              <button
                role="switch"
                aria-checked={checked}
                onClick={() => onChange(!checked)}
                className={clsx(
                  'relative mt-0.5 inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors',
                  checked ? 'bg-primary-600' : 'bg-slate-700',
                )}
              >
                <span
                  className={clsx(
                    'inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform',
                    checked ? 'translate-x-4' : 'translate-x-1',
                  )}
                />
              </button>
            </label>
          ))}

          {/* Top-K slider */}
          {includesAnalogs && (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Analog Count</span>
                <span className="font-mono font-medium text-slate-200">
                  {topKAnalogs}
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={20}
                value={topKAnalogs}
                onChange={(e) => setTopKAnalogs(Number(e.target.value))}
                className="w-full accent-primary-500 h-1.5 rounded-full bg-slate-700 cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-slate-600">
                <span>1</span>
                <span>20</span>
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* Generate button or status */}
      {!isActive ? (
        <button
          onClick={handleGenerate}
          disabled={isGenerating}
          className={clsx(
            'flex w-full items-center justify-center gap-2 rounded-xl py-3',
            'bg-primary-600 text-sm font-semibold text-white transition-all',
            'hover:bg-primary-500 active:scale-[0.98]',
            'disabled:cursor-not-allowed disabled:opacity-60',
          )}
        >
          {isGenerating ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Submitting…
            </>
          ) : (
            <>
              <FileText className="h-4 w-4" />
              Generate PDF Report
            </>
          )}
        </button>
      ) : (
        <Card>
          <div className="space-y-3">
            {/* Status row */}
            {statusConf && (
              <div className="flex items-center gap-2">
                <span className={statusConf.color}>{statusConf.icon}</span>
                <div>
                  <p className={clsx('text-sm font-semibold', statusConf.color)}>
                    {statusConf.label}
                  </p>
                  <p className="font-mono text-[11px] text-slate-500">
                    {report!.report_id.slice(0, 20)}…
                  </p>
                </div>
              </div>
            )}

            {/* Processing animation */}
            {(currentStatus === 'pending' || currentStatus === 'processing') && (
              <div className="space-y-1.5">
                {['Fetching region data', 'Building analog analysis', 'Rendering PDF'].map(
                  (step, i) => (
                    <div key={step} className="flex items-center gap-2 text-xs">
                      <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                      <span className="text-slate-400">{step}</span>
                    </div>
                  ),
                )}
              </div>
            )}

            {/* Download button */}
            {currentStatus === 'completed' && report?.pdf_url && (
              <a
                href={`${import.meta.env.VITE_API_BASE_URL ?? ''}${report.pdf_url}`}
                download
                target="_blank"
                rel="noreferrer"
                className="flex w-full items-center justify-center gap-2 rounded-lg
                           bg-emerald-600/20 border border-emerald-600/30 py-2.5
                           text-sm font-semibold text-emerald-400
                           hover:bg-emerald-600/30 transition-colors"
              >
                <Download className="h-4 w-4" />
                Download PDF Report
              </a>
            )}

            {/* Error message */}
            {(currentStatus === 'failed' || pollError || generateError) && (
              <ErrorMessage
                message={
                  report?.error_message ??
                  pollError ??
                  generateError ??
                  'Report generation failed'
                }
                compact
              />
            )}

            {/* Reset */}
            <button
              onClick={reset}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg
                         py-2 text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              <RefreshCw className="h-3 w-3" />
              Generate a new report
            </button>
          </div>
        </Card>
      )}

      {/* Info note */}
      <p className="text-center text-[11px] text-slate-600 px-2">
        Reports are generated asynchronously. Generation typically takes 10–30 seconds.
      </p>
    </div>
  );
}
