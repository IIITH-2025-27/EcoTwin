import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import type { SidebarTab, SimilarityMethod } from '@/types';

interface MapState {
  // ── Selected region ──────────────────────────────────────────────────────
  selectedRegionId: string | null;
  selectedRegionLat: number | null;
  selectedRegionLon: number | null;

  // ── UI State ─────────────────────────────────────────────────────────────
  activeTab: SidebarTab;
  topK: number;
  similarityMethod: SimilarityMethod;
  highlightedAnalogId: string | null;
  mapClickLoading: boolean;
  isSidebarCollapsed: boolean;

  // ── Actions ──────────────────────────────────────────────────────────────
  selectRegion: (
    id: string,
    lat: number,
    lon: number,
  ) => void;
  clearRegion: () => void;
  setActiveTab: (tab: SidebarTab) => void;
  setTopK: (k: number) => void;
  setSimilarityMethod: (method: SimilarityMethod) => void;
  setHighlightedAnalogId: (id: string | null) => void;
  setMapClickLoading: (loading: boolean) => void;
  toggleSidebar: () => void;
}

export const useMapStore = create<MapState>()(
  devtools(
    (set) => ({
      // Initial state
      selectedRegionId: null,
      selectedRegionLat: null,
      selectedRegionLon: null,
      activeTab: 'overview',
      topK: 5,
      similarityMethod: 'cosine' as SimilarityMethod,
      highlightedAnalogId: null,
      mapClickLoading: false,
      isSidebarCollapsed: false,

      // Actions
      selectRegion: (id, lat, lon) =>
        set(
          { selectedRegionId: id, selectedRegionLat: lat, selectedRegionLon: lon, activeTab: 'overview' },
          false,
          'selectRegion',
        ),

      clearRegion: () =>
        set(
          {
            selectedRegionId: null,
            selectedRegionLat: null,
            selectedRegionLon: null,
            activeTab: 'overview',
            highlightedAnalogId: null,
          },
          false,
          'clearRegion',
        ),

      setActiveTab: (tab) => set({ activeTab: tab }, false, 'setActiveTab'),

      setTopK: (k) => set({ topK: k }, false, 'setTopK'),

      setSimilarityMethod: (method) =>
        set({ similarityMethod: method }, false, 'setSimilarityMethod'),

      setHighlightedAnalogId: (id) =>
        set({ highlightedAnalogId: id }, false, 'setHighlightedAnalogId'),

      setMapClickLoading: (loading) =>
        set({ mapClickLoading: loading }, false, 'setMapClickLoading'),

      toggleSidebar: () =>
        set(
          (s) => ({ isSidebarCollapsed: !s.isSidebarCollapsed }),
          false,
          'toggleSidebar',
        ),
    }),
    { name: 'EcoTwinMapStore' },
  ),
);
