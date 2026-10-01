import { apiClient } from './client';

export interface PipelinePermissions {
  sync_lakes: boolean;
  fetch_images: boolean;
  merge_image_tiles: boolean;
  generate_embeddings: boolean;
  merge_embeddings: boolean;
  generate_features: boolean;
  fetch_b8: boolean;
}

export interface AppConfig {
  allow_data_pipeline_run: boolean;
  pipeline_permissions: PipelinePermissions;
}

export async function fetchAppConfig(): Promise<AppConfig> {
  const { data } = await apiClient.get<AppConfig>('/config');
  return data;
}
