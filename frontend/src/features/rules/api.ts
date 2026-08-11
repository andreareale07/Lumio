import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import type { Rule, RuleField, RuleOperator, RuleSuggestion } from "../../types/api";

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
