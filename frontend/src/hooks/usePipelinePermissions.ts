import { useQuery } from '@tanstack/react-query';
import { fetchAppConfig, type PipelinePermissions } from '@/api/config';

/**
 * Hook that fetches pipeline permission state from the backend.
 *
 * The backend / Supabase DB is the single source of truth.
 * Permissions are refetched every 60 seconds so that DB changes
 * propagate without a frontend redeployment or manual refresh.
 */
export function usePipelinePermissions() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['appConfig'],
    queryFn: fetchAppConfig,
    staleTime: 60_000,       // refetch every 60 s
    refetchInterval: 60_000, // auto-poll every 60 s
    retry: 2,
  });

  const masterEnabled = data?.allow_data_pipeline_run ?? false;
  const perms: PipelinePermissions = data?.pipeline_permissions ?? {
    sync_lakes: false,
    fetch_images: false,
    merge_image_tiles: false,
    generate_embeddings: false,
    merge_embeddings: false,
    generate_features: false,
    fetch_b8: false,
  };

  /**
   * Check whether a specific pipeline action is allowed.
   * Both the master switch AND the individual permission must be enabled.
   */
  function isPipelineActionAllowed(key: keyof PipelinePermissions): boolean {
    return masterEnabled && perms[key];
  }

  return {
    masterEnabled,
    permissions: perms,
    isPipelineActionAllowed,
    isLoading,
    error,
  };
}
