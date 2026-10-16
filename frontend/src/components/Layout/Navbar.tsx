import { useState } from 'react';
import { clsx } from 'clsx';
import {
  BarChart3,
  ChevronDown,
  Database,
  Layers,
  Leaf,
  PanelBottomClose,
  PanelBottomOpen,
  PanelLeftClose,
  PanelLeftOpen,
  Radar,
  RefreshCw,
  Satellite,
  Workflow,
} from 'lucide-react';
import { useMapStore } from '@/store/mapStore';
import { useRegion } from '@/hooks/useRegion';
import { usePipelinePermissions } from '@/hooks/usePipelinePermissions';
import SyncModal from '@/components/SyncModal/SyncModal';
import SyncLakesModal from '@/components/SyncModal/SyncLakesModal';
import FetchImagesModal from '@/components/SyncModal/FetchImagesModal';
import MergeTilesModal from '@/components/SyncModal/MergeTilesModal';
import MergeEmbeddingsModal from '@/components/SyncModal/MergeEmbeddingsModal';
import GenerateLakeFeaturesModal from '@/components/SyncModal/GenerateLakeFeaturesModal';
import FetchB8Modal from '@/components/SyncModal/FetchB8Modal';

const DENIED_TOOLTIP = 'Data Pipeline run Access denied';

export default function Navbar() {
  const { selectedRegionId, isSidebarCollapsed, toggleSidebar } = useMapStore();
  const { data: regionData } = useRegion(selectedRegionId);
  const { isPipelineActionAllowed } = usePipelinePermissions();
  const [showSync, setShowSync] = useState(false);
  const [showLakesSync, setShowLakesSync] = useState(false);
  const [showFetchImages, setShowFetchImages] = useState(false);
  const [showMergeTiles, setShowMergeTiles] = useState(false);
  const [showMergeEmbeddings, setShowMergeEmbeddings] = useState(false);
  const [showLakeFeatures, setShowLakeFeatures] = useState(false);
  const [showFetchB8, setShowFetchB8] = useState(false);
  const [showPipelineMenu, setShowPipelineMenu] = useState(false);

  const canSyncLakes = isPipelineActionAllowed('sync_lakes');
  const canFetchImages = isPipelineActionAllowed('fetch_images');
  const canMergeTiles = isPipelineActionAllowed('merge_image_tiles');
  const canGenerateEmbeddings = isPipelineActionAllowed('generate_embeddings');
  const canMergeEmbeddings = isPipelineActionAllowed('merge_embeddings');
  const canGenerateFeatures = isPipelineActionAllowed('generate_features');
  const canFetchB8 = isPipelineActionAllowed('fetch_b8');

  const pipelineActions = [
    {
      key: 'sync_lakes',
      label: 'Sync Lakes',
      description: 'Import HydroLAKES records into the lakes table',
      icon: <Database className="h-3.5 w-3.5" />,
      allowed: canSyncLakes,
      open: () => setShowLakesSync(true),
      className: 'border-primary-600/40 bg-primary-600/15 text-primary-300 hover:bg-primary-600/25 hover:text-primary-200',
    },
    {
      key: 'fetch_images',
      label: 'Fetch Images',
      description: 'Download Sentinel-2 GeoTIFF composites for active lakes',
      icon: <Satellite className="h-3.5 w-3.5" />,
      allowed: canFetchImages,
      open: () => setShowFetchImages(true),
      className: 'border-cyan-500/40 bg-cyan-500/15 text-cyan-300 hover:bg-cyan-500/25 hover:text-cyan-200',
    },
    {
      key: 'merge_image_tiles',
      label: 'Merge Image Tiles',
      description: 'Merge downloaded tiles into single GeoTIFFs per lake',
      icon: <Layers className="h-3.5 w-3.5" />,
      allowed: canMergeTiles,
      open: () => setShowMergeTiles(true),
      className: 'border-amber-500/40 bg-amber-500/15 text-amber-300 hover:bg-amber-500/25 hover:text-amber-200',
    },
    {
      key: 'generate_embeddings',
      label: 'Generate Embeddings',
      description: 'Generate embeddings from locally merged lake images',
      icon: <RefreshCw className="h-3.5 w-3.5" />,
      allowed: canGenerateEmbeddings,
      open: () => setShowSync(true),
      className: 'border-primary-600/40 bg-primary-600/15 text-primary-300 hover:bg-primary-600/25 hover:text-primary-200',
    },
    {
      key: 'merge_embeddings',
      label: 'Merge Embeddings',
      description: 'Aggregate lake tile embeddings into final lake embeddings in the regions table',
      icon: <RefreshCw className="h-3.5 w-3.5" />,
      allowed: canMergeEmbeddings,
      open: () => setShowMergeEmbeddings(true),
      className: 'border-purple-500/40 bg-purple-500/15 text-purple-300 hover:bg-purple-500/25 hover:text-purple-200',
    },
    {
      key: 'generate_features',
      label: 'Generate Lake Features',
      description: 'Extract ecological features from merged Sentinel-2 images',
      icon: <BarChart3 className="h-3.5 w-3.5" />,
      allowed: canGenerateFeatures,
      open: () => setShowLakeFeatures(true),
      className: 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 hover:text-emerald-200',
    },
    {
      key: 'fetch_b8',
      label: 'Fetch B8',
      description: 'Fetch Sentinel-2 B8 (NIR) band and compute zonal statistics per lake-year',
      icon: <Radar className="h-3.5 w-3.5" />,
      allowed: canFetchB8,
      open: () => setShowFetchB8(true),
      className: 'border-indigo-500/40 bg-indigo-500/15 text-indigo-300 hover:bg-indigo-500/25 hover:text-indigo-200',
    },
  ];

  return (
    <header className="flex h-14 flex-shrink-0 items-center justify-between gap-2 border-b border-slate-700/60 bg-surface-800/95 px-3 backdrop-blur-sm sm:px-4">
      {/* Left: logo + title */}
      <div className="flex min-w-0 items-center gap-2 sm:gap-3">
        <button
          onClick={toggleSidebar}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200 transition-colors"
          title={isSidebarCollapsed ? 'Show panel' : 'Hide panel'}
        >
          {isSidebarCollapsed ? (
            <>
              <PanelBottomOpen className="h-5 w-5 md:hidden" />
              <PanelLeftOpen className="hidden h-5 w-5 md:block" />
            </>
          ) : (
            <>
              <PanelBottomClose className="h-5 w-5 md:hidden" />
              <PanelLeftClose className="hidden h-5 w-5 md:block" />
            </>
          )}
        </button>

        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600/20 border border-primary-600/30">
            <Leaf className="h-4 w-4 text-primary-400" />
          </div>
          <div>
            <span className="text-sm font-bold tracking-wide text-slate-100">
              EcoTwin
            </span>
            <span className="ml-1.5 hidden text-xs text-slate-500 lg:inline">
              Ecosystem Discovery Platform
            </span>
          </div>
        </div>
      </div>

      {/* Center: selected region info */}
      {regionData && (
        <div className="hidden items-center gap-4 md:flex">
          <div className="text-center">
            <p className="text-xs text-slate-500">Region</p>
            <p className="font-mono text-xs text-slate-300">
              {regionData.region.region_id.slice(0, 8)}…
            </p>
          </div>
          <div className="text-center">
            <p className="text-xs text-slate-500">Lat / Lon</p>
            <p className="font-mono text-xs text-slate-300">
              {regionData.region.center_lat.toFixed(4)},{' '}
              {regionData.region.center_lon.toFixed(4)}
            </p>
          </div>
          {regionData.latest_features?.dominant_ecosystem && (
            <div className="text-center">
              <p className="text-xs text-slate-500">Ecosystem</p>
              <p className="text-xs text-primary-400 capitalize">
                {regionData.latest_features.dominant_ecosystem}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Right: sync actions + status */}
      <div className="flex items-center gap-3">
        {/* Inline pipeline buttons (2xl and up) */}
        <div className="hidden items-center gap-2 2xl:flex">
          {pipelineActions.map((action) => (
            <button
              key={action.key}
              onClick={() => action.allowed && action.open()}
              disabled={!action.allowed}
              className={clsx(
                'flex items-center gap-1.5 whitespace-nowrap rounded-lg border px-3 py-1.5 text-xs font-medium',
                'transition-colors disabled:cursor-not-allowed disabled:opacity-50',
                action.className,
              )}
              title={action.allowed ? action.description : DENIED_TOOLTIP}
            >
              {action.icon}
              <span>{action.label}</span>
            </button>
          ))}
        </div>

        {/* Collapsed pipeline menu (below 2xl) */}
        <div className="relative 2xl:hidden">
          <button
            onClick={() => setShowPipelineMenu((open) => !open)}
            className="flex items-center gap-1.5 rounded-lg border border-slate-600/60 bg-slate-700/30 px-3 py-1.5
                       text-xs font-medium text-slate-300 hover:bg-slate-700/60 hover:text-slate-100 transition-colors"
            aria-haspopup="menu"
            aria-expanded={showPipelineMenu}
            title="Data pipeline actions"
          >
            <Workflow className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Pipeline</span>
            <ChevronDown className={clsx('h-3.5 w-3.5 transition-transform', showPipelineMenu && 'rotate-180')} />
          </button>

          {showPipelineMenu && (
            <>
              <div className="fixed inset-0 z-[1500]" onClick={() => setShowPipelineMenu(false)} />
              <div
                role="menu"
                className="absolute right-0 top-full z-[1501] mt-2 w-64 max-w-[calc(100vw-2rem)] space-y-1 rounded-xl
                           border border-slate-700/60 bg-surface-800 p-2 shadow-2xl"
              >
                {pipelineActions.map((action) => (
                  <button
                    key={action.key}
                    role="menuitem"
                    onClick={() => {
                      if (!action.allowed) return;
                      setShowPipelineMenu(false);
                      action.open();
                    }}
                    disabled={!action.allowed}
                    className={clsx(
                      'flex w-full items-center gap-2 rounded-lg border px-3 py-2.5 text-left text-xs font-medium',
                      'transition-colors disabled:cursor-not-allowed disabled:opacity-50',
                      action.className,
                    )}
                    title={action.allowed ? action.description : DENIED_TOOLTIP}
                  >
                    {action.icon}
                    <span>{action.label}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="hidden items-center gap-1.5 sm:flex">
          <span className="h-1.5 w-1.5 rounded-full bg-primary-500 animate-pulse" />
          <span className="text-xs text-slate-400">
            {selectedRegionId ? 'Region selected' : 'Click map to explore'}
          </span>
        </div>
      </div>

      {showSync && <SyncModal onClose={() => setShowSync(false)} />}
      {showLakesSync && <SyncLakesModal onClose={() => setShowLakesSync(false)} />}
      {showFetchImages && <FetchImagesModal onClose={() => setShowFetchImages(false)} />}
      {showMergeTiles && <MergeTilesModal onClose={() => setShowMergeTiles(false)} />}
      {showMergeEmbeddings && <MergeEmbeddingsModal onClose={() => setShowMergeEmbeddings(false)} />}
      {showLakeFeatures && <GenerateLakeFeaturesModal onClose={() => setShowLakeFeatures(false)} />}
      {showFetchB8 && <FetchB8Modal onClose={() => setShowFetchB8(false)} />}
    </header>
  );
}
