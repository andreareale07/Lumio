import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import { streamSse } from "../imports/api";
import type {
  JobRun,
  ReclassificationPreview,
  ReclassificationScope,
  ReclassifyTriggered,
  Rule,
  RuleField,
  RuleOperator,
  RuleSuggestion,
} from "../../types/api";

export const rulesKey = ["rules"] as const;
export const ruleSuggestionsKey = ["rules", "suggestions"] as const;

export function useRules() {
  return useQuery({
    queryKey: rulesKey,
    queryFn: () => api.get<Rule[]>("/rules"),
  });
}

export function useRuleSuggestions() {
  return useQuery({
    queryKey: ruleSuggestionsKey,
    queryFn: () => api.get<RuleSuggestion[]>("/rules/suggestions"),
  });
}

export interface RuleInput {
  name: string;
  field: RuleField;
  operator: RuleOperator;
  value: string;
  category_id: string;
  priority?: number;
  is_active?: boolean;
}

function invalidateRules(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: rulesKey });
  queryClient.invalidateQueries({ queryKey: ruleSuggestionsKey });
}

export function useCreateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: RuleInput) => api.post<Rule>("/rules", input),
    onSuccess: () => invalidateRules(queryClient),
  });
}

export function useUpdateRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: Partial<RuleInput> & { id: string }) =>
      api.patch<Rule>(`/rules/${id}`, input),
    onSuccess: () => invalidateRules(queryClient),
  });
}

export function useDeleteRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/rules/${id}`),
    onSuccess: () => invalidateRules(queryClient),
  });
}

// --- Riclassificazione (riapplica regole/AI a transazioni già importate) --

export function useReclassificationPreview(scope: ReclassificationScope) {
  return useQuery({
    queryKey: ["classification", "reclassify", "preview", scope] as const,
    queryFn: () =>
      api.get<ReclassificationPreview>(`/classification/reclassify/preview?scope=${scope}`),
  });
}

export const reclassificationStatusKey = ["classification", "reclassify", "status"] as const;

export function useReclassificationStatus() {
  return useQuery({
    queryKey: reclassificationStatusKey,
    queryFn: () => api.get<JobRun | null>("/classification/reclassify/status"),
  });
}

export function useTriggerReclassification() {
  return useMutation({
    mutationFn: (input: { scope: ReclassificationScope; run_ai: boolean }) =>
      api.post<ReclassifyTriggered>("/classification/reclassify", input),
  });
}

export interface ReclassificationProgressEvent {
  event: string;
  processed?: number;
  total?: number;
  detail?: string;
}

/** Stesso streamSse riusato da imports/api.ts (fetch()+ReadableStream, non
 * EventSource — serve l'header Authorization). */
export function streamReclassificationEvents(
  onEvent: (event: ReclassificationProgressEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  return streamSse("/classification/reclassify/events", onEvent, signal);
}
