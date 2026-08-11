import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../../lib/apiClient";
import type {
  AIConnectionCheckRequest,
  AIModelListResult,
  AIProfile,
  AIProfileCreate,
  AIProfileUpdate,
  AITestConnectionResult,
} from "../../../types/api";

export const aiProfilesKey = ["settings", "ai", "profiles"] as const;

export function useAIProfiles() {
  return useQuery({
    queryKey: aiProfilesKey,
    queryFn: () => api.get<AIProfile[]>("/settings/ai/profiles"),
  });
}

function invalidateProfiles(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: aiProfilesKey });
}

export function useCreateAIProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: AIProfileCreate) => api.post<AIProfile>("/settings/ai/profiles", input),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

export function useUpdateAIProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: AIProfileUpdate & { id: string }) =>
      api.patch<AIProfile>(`/settings/ai/profiles/${id}`, input),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

export function useDeleteAIProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/settings/ai/profiles/${id}`),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

export function useActivateAIProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<AIProfile>(`/settings/ai/profiles/${id}/activate`),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

export function useDeactivateAI() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<void>("/settings/ai/deactivate"),
    onSuccess: () => invalidateProfiles(queryClient),
  });
}

export function useTestDraftConnection() {
  return useMutation({
    mutationFn: (input: AIConnectionCheckRequest) =>
      api.post<AITestConnectionResult>("/settings/ai/test", input),
  });
}

export function useListDraftModels() {
  return useMutation({
    mutationFn: (input: AIConnectionCheckRequest) => api.post<AIModelListResult>("/settings/ai/models", input),
  });
}

export function useTestSavedProfile() {
  return useMutation({
    mutationFn: (id: string) => api.post<AITestConnectionResult>(`/settings/ai/profiles/${id}/test`),
  });
}

export function useListSavedProfileModels() {
  return useMutation({
    mutationFn: (id: string) => api.post<AIModelListResult>(`/settings/ai/profiles/${id}/models`),
  });
}
