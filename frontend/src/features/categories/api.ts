import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import type { Category } from "../../types/api";

export const categoriesKey = ["categories"] as const;

export function useCategories() {
  return useQuery({
    queryKey: categoriesKey,
    queryFn: () => api.get<Category[]>("/categories"),
    staleTime: 5 * 60 * 1000,
  });
}

export interface CreateCategoryInput {
  name: string;
  parent_id?: string | null;
}

const DIACRITICS_PATTERN = new RegExp("[̀-ͯ]", "g");

function slugify(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(DIACRITICS_PATTERN, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export function useCreateCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateCategoryInput) =>
      api.post<Category>("/categories", { ...input, code: slugify(input.name) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: categoriesKey }),
  });
}
