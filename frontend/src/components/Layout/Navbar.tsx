import { useState } from 'react';
import { Database, Layers, Leaf, PanelLeftClose, PanelLeftOpen, RefreshCw, Satellite } from 'lucide-react';
import { useMapStore } from '@/store/mapStore';
import { useRegion } from '@/hooks/useRegion';
import SyncModal from '@/components/SyncModal/SyncModal';
import SyncLakesModal from '@/components/SyncModal/SyncLakesModal';
import FetchImagesModal from '@/components/SyncModal/FetchImagesModal';
import MergeTilesModal from '@/components/SyncModal/MergeTilesModal';

export default function Navbar() {
  const { selectedRegionId, isSidebarCollapsed, toggleSidebar } = useMapStore();
  const { data: regionData } = useRegion(selectedRegionId);
  const [showSync, setShowSync] = useState(false);
  const [showLakesSync, setShowLakesSync] = useState(false);
  const [showFetchImages, setShowFetchImages] = useState(false);
  const [showMergeTiles, setShowMergeTiles] = useState(false);

  return (
    <header className="flex h-14 items-center justify-between border-b border-slate-700/60 bg-surface-800/95 px-4 backdrop-blur-sm">
      {/* Left: logo + title */}
      <div className="flex items-center gap-3">
        <button
          onClick={toggleSidebar}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-700/50 hover:text-slate-200 transition-colors"
          title={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {isSidebarCollapsed ? (
            <PanelLeftOpen className="h-5 w-5" />
          ) : (
            <PanelLeftClose className="h-5 w-5" />
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
            <span className="ml-1.5 hidden text-xs text-slate-500 sm:inline">
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

      {/* Right: sync actions + version tag */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => setShowLakesSync(true)}
          className="flex items-center gap-1.5 rounded-lg border border-primary-600/40 bg-primary-600/15 px-3 py-1.5
                     text-xs font-medium text-primary-300 hover:bg-primary-600/25 hover:text-primary-200
                     transition-colors"
          title="Import HydroLAKES records into the lakes table"
        >
          <Database className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Sync Lakes</span>
        </button>
        <button
          onClick={() => setShowFetchImages(true)}
          className="flex items-center gap-1.5 rounded-lg border border-cyan-500/40 bg-cyan-500/15 px-3 py-1.5
                     text-xs font-medium text-cyan-300 hover:bg-cyan-500/25 hover:text-cyan-200
                     transition-colors"
          title="Download Sentinel-2 GeoTIFF composites for active lakes"
        >
          <Satellite className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Fetch Images</span>
        </button>
        <button
          onClick={() => setShowMergeTiles(true)}
          className="flex items-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/15 px-3 py-1.5
                     text-xs font-medium text-amber-300 hover:bg-amber-500/25 hover:text-amber-200
                     transition-colors"
          title="Merge downloaded tiles into single GeoTIFFs per lake"
        >
          <Layers className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Merge Image Tiles</span>
        </button>
        <button
          onClick={() => setShowSync(true)}
          className="flex items-center gap-1.5 rounded-lg border border-primary-600/40 bg-primary-600/15 px-3 py-1.5
                     text-xs font-medium text-primary-300 hover:bg-primary-600/25 hover:text-primary-200
                     transition-colors"
          title="Generate embeddings from locally merged lake images"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">Generate Embeddings</span>
        </button>
        <span className="hidden rounded-md bg-slate-700/40 px-2 py-0.5 font-mono text-xs text-slate-500 sm:inline">
          v1.0.0
        </span>
        <div className="flex items-center gap-1.5">
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
    </header>
  );
}
