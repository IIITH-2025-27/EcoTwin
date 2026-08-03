import { clsx } from 'clsx';
import {
  LayoutDashboard,
  Network,
  LineChart,
  TrendingUp,
  FileText,
  ChevronRight,
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
function Sidebar() {
  const {
    activeTab,
    setActiveTab,
    selectedRegionId,
    selectedLake,
    setSelectedLake,
    clearRegion,
  } = useMapStore();

  return (
    <aside className="flex h-full flex-col border-r border-slate-700/60 bg-surface-900">
      {/* Tab bar */}
      <div className="border-b border-slate-700/60 bg-surface-800/50">
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

        {/* Tabs */}
        <div className="flex overflow-x-auto">
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

// ── MapPage ────────────────────────────────────────────────────────────────
export default function MapPage() {
  const { isSidebarCollapsed } = useMapStore();

  return (
    <div className="flex h-screen flex-col bg-surface-900">
      {/* Navbar */}
      <Navbar />

      {/* Main area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <div
          className={clsx(
            'transition-all duration-300 ease-in-out',
            isSidebarCollapsed ? 'w-0 overflow-hidden' : 'w-[360px] min-w-[360px]',
          )}
        >
          <Sidebar />
        </div>

        {/* Map */}
        <main className="relative flex-1 overflow-hidden">
          <EcoTwinMap />
        </main>
      </div>
    </div>
  );
}
