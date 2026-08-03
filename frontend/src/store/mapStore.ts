import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import type { SidebarTab, SimilarityMethod } from '@/types';
import type { LakeGeometry } from '@/types';

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
  focusedAnalogRegionId: string | null;
  focusedAnalogFocusRevision: number;
  mapClickLoading: boolean;
  selectedLake: LakeGeometry | null;
  selectedLakeFocusRevision: number;
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
  setFocusedAnalogRegionId: (id: string | null) => void;
  setMapClickLoading: (loading: boolean) => void;
  setSelectedLake: (lake: LakeGeometry | null) => void;
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
      focusedAnalogRegionId: null,
      focusedAnalogFocusRevision: 0,
      mapClickLoading: false,
      selectedLake: null,
      selectedLakeFocusRevision: 0,
      isSidebarCollapsed: false,

      // Actions
      selectRegion: (id, lat, lon) =>
        set(
          {
            selectedRegionId: id,
            selectedRegionLat: lat,
            selectedRegionLon: lon,
            activeTab: 'overview',
            focusedAnalogRegionId: null,
          },
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
            focusedAnalogRegionId: null,
            selectedLake: null,
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

      setFocusedAnalogRegionId: (id) =>
        set(
          (state) => ({
            focusedAnalogRegionId: id,
            focusedAnalogFocusRevision: state.focusedAnalogFocusRevision + 1,
          }),
          false,
          'setFocusedAnalogRegionId',
        ),

      setMapClickLoading: (loading) =>
        set({ mapClickLoading: loading }, false, 'setMapClickLoading'),

      setSelectedLake: (lake) =>
        set(
          (state) => ({
            selectedLake: lake,
            selectedLakeFocusRevision: state.selectedLakeFocusRevision + 1,
          }),
          false,
          'setSelectedLake',
        ),

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
