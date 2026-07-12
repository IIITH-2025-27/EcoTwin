// ── Region ────────────────────────────────────────────────────────────────

export interface Region {
  region_id: string;
  hydrolake_id: string;
  name: string;
  country: string;
  center_lat: number;
  center_lon: number;
  area_sqkm: number;
  bbox: Record<string, number> | null;
  created_at: string;
  updated_at: string;
}

export interface RegionMapFeature extends Region {
  geometry: GeoJSON.Geometry | null;
}

export interface RegionFeature {
  region_id: string;
  year: number;
  ndvi_mean: number | null;
  ndvi_std: number | null;
  ndvi_median: number | null;
  ndvi_min: number | null;
  ndvi_max: number | null;
  ndwi_mean: number | null;
  ndwi_std: number | null;
  ndwi_median: number | null;
  ndwi_min: number | null;
  ndwi_max: number | null;
  nbr_mean: number | null;
  nbr_std: number | null;
  nbr_median: number | null;
  nbr_min: number | null;
  nbr_max: number | null;
  dominant_ecosystem: string | null;
}

export interface RegionSummary {
  region: Region;
  latest_features: RegionFeature | null;
}

export interface RegionQueryRequest {
  lat: number;
  lon: number;
}

export interface RegionQueryResult {
  region_id: string;
  center_lat: number;
  center_lon: number;
  distance_km: number;
}

export interface LakeRegionResponse {
  region_id: string;
  hydrolake_id: string;
  name: string;
  country: string;
  center_lat: number;
  center_lon: number;
  area_sqkm: number;
  bbox: Record<string, number> | null;
  geometry: GeoJSON.Geometry | null;
  created_at: string;
  updated_at: string;
}

export interface LakeSearchResult {
  lake_id: number;
  display_name: string;
  state: string | null;
  area_sqkm: number | null;
}

export interface LakeGeometry extends LakeSearchResult {
  country: string;
  center_lat: number | null;
  center_lon: number | null;
  geometry: GeoJSON.Geometry | null;
}

// ── Similarity ────────────────────────────────────────────────────────────

export type SimilarityMethod = 'cosine' | 'euclidean' | 'knn';

export interface AnalogResult {
  region_id: string;
  center_lat: number;
  center_lon: number;
  similarity_score: number;
  year: number;
  dominant_ecosystem: string | null;
}

export interface SimilarityResponse {
  query_region_id: string;
  query_year: number;
  analogs: AnalogResult[];
  search_latency_ms: number;
  method: SimilarityMethod;
}

// ── Temporal ──────────────────────────────────────────────────────────────

export interface YearlyIndicator {
  year: number;
  value: number;
}

export interface TemporalData {
  region_id: string;
  ndvi: YearlyIndicator[];
  ndwi: YearlyIndicator[];
  nbr: YearlyIndicator[];
}

// ── Forecast ──────────────────────────────────────────────────────────────

export type TrendDirection = 'increasing' | 'stable' | 'declining';

export interface ForecastHorizon {
  year: number;
  ndvi_forecast: number;
  ndwi_forecast: number;
  nbr_forecast: number;
  confidence: number;
}

export interface ForecastData {
  region_id: string;
  current_year: number;
  forecast_horizons: ForecastHorizon[];
  best_analog_id: string | null;
  analog_match_year: number | null;
  overall_confidence: number;
  vegetation_trend: TrendDirection;
  water_trend: TrendDirection;
  burn_severity_trend: TrendDirection;
  explanation: string;
}

// ── Report ────────────────────────────────────────────────────────────────

export type ReportStatus = 'pending' | 'processing' | 'completed' | 'failed';

export interface Report {
  report_id: string;
  region_id: string;
  status: ReportStatus;
  generated_at: string;
  pdf_url: string | null;
  error_message: string | null;
}

export interface ReportRequest {
  region_id: string;
  include_forecast: boolean;
  include_analogs: boolean;
  top_k_analogs: number;
}

export interface LakeSyncRequest {
  country: string;
  duration: import('@/api/sync').SyncDuration;
  sync_mode: import('@/api/sync').SyncMode;
  confirmed: true;
}

// ── Common ────────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string;
  code: string;
}

// ── UI helpers ────────────────────────────────────────────────────────────

export type SidebarTab = 'overview' | 'analogs' | 'temporal' | 'forecast' | 'report';
