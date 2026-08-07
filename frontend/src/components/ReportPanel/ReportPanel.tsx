import {
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  RefreshCw,
} from 'lucide-react';
import { clsx } from 'clsx';
import Card from '@/components/common/Card';
import ErrorMessage from '@/components/common/ErrorMessage';
import { useReport } from '@/hooks/useReport';
import { useMapStore } from '@/store/mapStore';
import type { SimilarityMethod } from '@/types';

const METHODS: SimilarityMethod[] = ['cosine', 'euclidean', 'knn'];

export default function ReportPanel() {
  const { selectedLake, topK, setTopK, similarityMethod, setSimilarityMethod } =
    useMapStore();
  const { steps, stepIndex, generate, isGenerating, isSuccess, error, reset } =
    useReport();

  if (!selectedLake) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-12 text-center px-4">
        <FileText className="h-10 w-10 text-slate-700" />
        <p className="text-sm text-slate-400">
          Select a lake on the map to generate its ecosystem report
        </p>
      </div>
    );
  }

  const handleGenerate = () => {
    generate({
      lake_id: selectedLake.lake_id,
      top_k: topK,
      method: similarityMethod,
    });
  };

  const handleReset = () => {
    reset();
  };

  const showSuccess = isSuccess && !isGenerating && !error;

  return (
    <div className="space-y-3 p-3 tab-content-enter">
      {/* Selected lake */}
      <Card title="Report Options">
        <div className="mb-3 rounded-lg bg-slate-800/60 border border-slate-700/60 px-3 py-2">
          <p className="text-sm font-medium text-slate-200">
            {selectedLake.display_name}
          </p>
          <p className="text-xs text-slate-500">
            {[selectedLake.state, selectedLake.country]
              .filter(Boolean)
              .join(' · ') || '—'}
          </p>
        </div>

        {/* Top-K slider */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400">Analog Lakes (Top-K)</span>
            <span className="font-mono font-medium text-slate-200">{topK}</span>
          </div>
          <input
            type="range"
            min={1}
            max={20}
            value={topK}
            onChange={(e) => setTopK(Number(e.target.value))}
            className="w-full accent-primary-500 h-1.5 rounded-full bg-slate-700 cursor-pointer"
          />
          <div className="flex justify-between text-[10px] text-slate-600">
            <span>1</span>
            <span>20</span>
          </div>
        </div>

        {/* Similarity method */}
        <div className="space-y-1.5 pt-2">
          <span className="text-xs text-slate-400">Similarity Method</span>
          <div className="grid grid-cols-3 gap-2">
            {METHODS.map((method) => (
              <button
                key={method}
                onClick={() => setSimilarityMethod(method)}
                className={clsx(
                  'rounded-lg border px-2 py-1.5 text-xs font-medium capitalize transition-colors',
                  similarityMethod === method
                    ? 'border-primary-500 bg-primary-600/20 text-primary-300'
                    : 'border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-200',
                )}
              >
                {method}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* Generate button */}
      {!isGenerating && !showSuccess && (
        <button
          onClick={handleGenerate}
          className={clsx(
            'flex w-full items-center justify-center gap-2 rounded-xl py-3',
            'bg-primary-600 text-sm font-semibold text-white transition-all',
            'hover:bg-primary-500 active:scale-[0.98]',
          )}
        >
          <FileText className="h-4 w-4" />
          Generate PDF Report
        </button>
      )}

      {/* Progress checklist */}
      {isGenerating && (
        <Card title="Generating Report">
          <div className="space-y-1.5">
            {steps.map((step, i) => (
              <div key={step} className="flex items-center gap-2 text-xs">
                {i < stepIndex ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                ) : i === stepIndex ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-400" />
                ) : (
                  <span className="h-3.5 w-3.5 rounded-full border border-slate-600" />
                )}
                <span
                  className={clsx(
                    i <= stepIndex ? 'text-slate-200' : 'text-slate-500',
                  )}
                >
                  {step}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Success */}
      {showSuccess && (
        <Card>
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="h-5 w-5 text-emerald-400" />
            <div>
              <p className="text-sm font-semibold text-emerald-400">
                Report generated
              </p>
              <p className="text-xs text-slate-400">
                The PDF has been opened in a new tab.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Error */}
      {error && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <XCircle className="h-4 w-4 text-red-400" />
            <span className="text-sm font-semibold text-red-400">
              Generation failed
            </span>
          </div>
          <ErrorMessage message={error} compact />
        </div>
      )}

      {/* Reset */}
      {(showSuccess || error) && (
        <button
          onClick={handleReset}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg
                     py-2 text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          <RefreshCw className="h-3 w-3" />
          Generate a new report
        </button>
      )}

      {/* Info note */}
      <p className="text-center text-[11px] text-slate-600 px-2">
        The generated report opens in a new tab. Generation typically takes
        10–30 seconds. The Forecast section is currently under development.
      </p>
    </div>
  );
}
