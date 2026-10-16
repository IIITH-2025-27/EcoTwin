import { useRef } from 'react';
import { clsx } from 'clsx';
import {
  LayoutDashboard,
  Network,
  LineChart,
  TrendingUp,
  FileText,
  ChevronRight,
  ChevronsDown,
  ChevronsUp,
  X,
} from 'lucide-react';
import Navbar from '@/components/Layout/Navbar';
import EcoTwinMap from '@/components/Map/EcoTwinMap';
import RegionPanel from '@/components/RegionPanel/RegionPanel';
import AnalogPanel from '@/components/AnalogPanel/AnalogPanel';
import TemporalChart from '@/components/TemporalChart/TemporalChart';
import ForecastPanel from '@/components/ForecastPanel/ForecastPanel';
import ReportPanel from '@/components/ReportPanel/ReportPanel';
import { useMapStore } from '@/store/mapStore';
import { useSheetDrag } from '@/hooks/useSheetDrag';
import type { SidebarTab } from '@/types';

// ── Sidebar tab definition ────────────────────────────────────────────────
const TABS: Array<{
  id: SidebarTab;
  label: string;
  icon: React.ReactNode;
  requiresRegion: boolean;
}> = [
  {
    id: 'overview',
    label: 'Overview',
    icon: <LayoutDashboard className="h-4 w-4" />,
    requiresRegion: false,
  },
  {
    id: 'analogs',
    label: 'Analogs',
    icon: <Network className="h-4 w-4" />,
    requiresRegion: true,
  },
  // {
  //   id: 'temporal',
  //   label: 'Temporal',
  //   icon: <LineChart className="h-4 w-4" />,
  //   requiresRegion: true,
  // },
  {
    id: 'forecast',
    label: 'Forecast',
    icon: <TrendingUp className="h-4 w-4" />,
    requiresRegion: true,
  },
  {
    id: 'report',
    label: 'Report',
    icon: <FileText className="h-4 w-4" />,
    requiresRegion: true,
  },
];

// ── Sidebar component ─────────────────────────────────────────────────────
type DragHandlers = ReturnType<typeof useSheetDrag>['handlers'];

function Sidebar({ dragHandlers }: { dragHandlers: DragHandlers }) {
  const {
    activeTab,
    setActiveTab,
    selectedRegionId,
    selectedLake,
    setSelectedLake,
    clearRegion,
    setSidebarCollapsed,
  } = useMapStore();

  return (
    <aside
      className="flex h-full flex-col overflow-hidden rounded-t-2xl border-t border-slate-700/60 bg-surface-900 shadow-2xl
                 md:rounded-none md:border-r md:border-t-0 md:shadow-none"
    >
      {/* Tab bar */}
      <div className="border-b border-slate-700/60 bg-surface-800/50">
        {/* Bottom-sheet handle (mobile only): drag to resize, tap to minimize */}
        <button
          type="button"
          {...dragHandlers}
          onClick={() => setSidebarCollapsed(true)}
          className="flex w-full cursor-grab touch-none items-center justify-center py-3 active:cursor-grabbing md:hidden"
          aria-label="Drag to resize, tap to minimize"
          title="Drag to resize, tap to minimize"
        >
          <span className="h-1 w-10 rounded-full bg-slate-600" />
        </button>

        {/* Clear region button */}
        {selectedRegionId && (
          <div className="flex items-center justify-between border-b border-slate-700/40 px-3 py-2">
            <span className="text-xs text-slate-500">Region active</span>
            <button
              onClick={clearRegion}
              className="flex items-center gap-1 rounded-md px-2 py-0.5 text-xs text-slate-500
                         hover:bg-slate-700/50 hover:text-slate-300 transition-colors"
            >
              <X className="h-3 w-3" />
              Clear
            </button>
          </div>
        )}

        {selectedRegionId && selectedLake && (
          <div className="border-b border-slate-700/40 px-3 py-1">
            <button
              type="button"
              onClick={() => setSelectedLake(selectedLake)}
              className="w-full rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-left transition-colors hover:border-emerald-400/50 hover:bg-emerald-500/15"
              title="Refocus this lake on the map"
            >
              <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald-300/80">
                Selected Lake
              </p>
              <p className="mt-0.5 truncate text-sm font-semibold text-slate-100">
                {selectedLake.display_name}
              </p>
              {/* <p className="mt-1 text-xs text-slate-400">
                {selectedLake.area_sqkm != null
                  ? `${selectedLake.area_sqkm.toFixed(2)} km²`
                  : 'Area unavailable'}
              </p> */}
            </button>
          </div>
        )}

        {/* Tabs — on mobile these live in the bottom nav bar instead */}
        <div className="hidden overflow-x-auto md:flex">
          {TABS.map((tab) => {
            const disabled = tab.requiresRegion && !selectedRegionId;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => !disabled && setActiveTab(tab.id)}
                disabled={disabled}
                title={disabled ? 'Select a region first' : tab.label}
                className={clsx(
                  'flex flex-1 flex-col items-center gap-1 border-b-2 px-2 py-2.5 text-center',
                  'transition-all text-[10px] font-medium',
                  isActive
                    ? 'border-primary-500 text-primary-400'
                    : disabled
                    ? 'cursor-not-allowed border-transparent text-slate-700'
                    : 'border-transparent text-slate-500 hover:border-slate-600 hover:text-slate-300',
                )}
              >
                <span className={isActive ? 'text-primary-400' : ''}>{tab.icon}</span>
                <span className="hidden sm:block">{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Tab content — scrollable */}
      <div className="flex-1 overflow-y-auto scrollbar-thin">
        {activeTab === 'overview' && <RegionPanel />}
        {activeTab === 'analogs' && <AnalogPanel />}
        {activeTab === 'temporal' && <TemporalChart />}
        {activeTab === 'forecast' && <ForecastPanel />}
        {activeTab === 'report' && <ReportPanel />}
      </div>
    </aside>
  );
}

// ── Mobile bottom nav (Amazon-style tab bar) ─────────────────────────────
function MobileBottomNav({ dragHandlers }: { dragHandlers: DragHandlers }) {
  const {
    activeTab,
    setActiveTab,
    selectedRegionId,
    isSidebarCollapsed,
    setSidebarCollapsed,
  } = useMapStore();

  return (
    // Dragging up on the bar pulls the panel open; taps still select tabs
    <nav
      {...dragHandlers}
      className="flex flex-shrink-0 touch-none border-t border-slate-700/60 bg-surface-800 pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      {TABS.map((tab) => {
        const disabled = tab.requiresRegion && !selectedRegionId;
        const isActive = activeTab === tab.id && !isSidebarCollapsed;
        return (
          <button
            key={tab.id}
            onClick={() => {
              if (disabled) return;
              setActiveTab(tab.id);
              setSidebarCollapsed(false);
            }}
            disabled={disabled}
            className={clsx(
              'relative flex flex-1 flex-col items-center gap-1 py-2 text-[10px] font-medium transition-colors',
              isActive
                ? 'text-primary-400'
                : disabled
                ? 'cursor-not-allowed text-slate-700'
                : 'text-slate-400 active:text-slate-200',
            )}
          >
            {/* Active indicator bar */}
            <span
              className={clsx(
                'absolute inset-x-4 top-0 h-0.5 rounded-b-full',
                isActive ? 'bg-primary-500' : 'bg-transparent',
              )}
            />
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        );
      })}

      <button
        onClick={() => setSidebarCollapsed(!isSidebarCollapsed)}
        className="flex flex-1 flex-col items-center gap-1 border-l border-slate-700/60 py-2 text-[10px] font-medium
                   text-slate-400 transition-colors active:text-slate-200"
        aria-label={isSidebarCollapsed ? 'Expand panel' : 'Minimize panel'}
      >
        {isSidebarCollapsed ? <ChevronsUp className="h-4 w-4" /> : <ChevronsDown className="h-4 w-4" />}
        <span>{isSidebarCollapsed ? 'Expand' : 'Minimize'}</span>
      </button>
    </nav>
  );
}

// ── MapPage ────────────────────────────────────────────────────────────────
export default function MapPage() {
  const { isSidebarCollapsed, sheetHeight } = useMapStore();
  const mainRef = useRef<HTMLDivElement>(null);
  const { handlers: dragHandlers, liveHeight } = useSheetDrag(mainRef);
  const isDragging = liveHeight !== null;
  const sheetHidden = isSidebarCollapsed && !isDragging;

  return (
    <div className="flex h-dvh flex-col bg-surface-900">
      {/* Navbar */}
      <Navbar />

      {/* Main area */}
      <div ref={mainRef} className="relative flex flex-1 overflow-hidden">
        {/* Sidebar — bottom sheet over the map on mobile, side column from md up */}
        <div
          className={clsx(
            'absolute inset-x-0 bottom-0 z-[1200] h-[var(--sheet-h)] ease-in-out',
            isDragging ? 'transition-none' : 'transition-transform duration-300',
            'md:relative md:inset-auto md:z-auto md:h-auto md:translate-y-0 md:transition-all',
            sheetHidden
              ? 'pointer-events-none translate-y-full md:w-0 md:min-w-0 md:overflow-hidden'
              : 'translate-y-0 md:w-[360px] md:min-w-[360px]',
          )}
          style={{ '--sheet-h': `${(liveHeight ?? sheetHeight) * 100}%` } as React.CSSProperties}
          aria-hidden={sheetHidden}
        >
          <Sidebar dragHandlers={dragHandlers} />
        </div>

        {/* Map */}
        <main className="relative flex-1 overflow-hidden">
          <EcoTwinMap />
        </main>
      </div>

      {/* Mobile bottom tab bar */}
      <MobileBottomNav dragHandlers={dragHandlers} />
    </div>
  );
}
