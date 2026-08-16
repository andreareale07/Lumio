import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../lib/apiClient";
import type { Category, CategoryKind } from "../../types/api";

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
  // Rilevante solo per una categoria di primo livello: su una sottocategoria
  // il backend lo ignora e la eredita comunque dal padre (validate_kind_matches_parent),
  // quindi non ha senso lasciarlo inviare in quel caso dal form.
  kind?: CategoryKind;
  sort_order?: number;
}

export function useCreateCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    // `code` non e' piu' un campo di input (rework tassonomia): generato
    // server-side da `category_service.generate_code` — prefisso del padre
    // + slug, con suffisso anti-collisione. Lo slugify client-side rotto
    // (nessun prefisso del padre, causa storica di code non-dot-notation)
    // e' stato rimosso, non corretto: non serve piu' a nulla.
    mutationFn: (input: CreateCategoryInput) => api.post<Category>("/categories", input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: categoriesKey }),
  });
}

export interface UpdateCategoryInput {
  id: string;
  name?: string;
  parent_id?: string | null;
  kind?: CategoryKind;
  sort_order?: number;
  is_active?: boolean;
}

/** Milestone 06.5 (audit retroattivo): a differenza della creazione al volo
 * di useCreateCategory, qui non si rigenera `code` — modificare il nome di
 * una categoria esistente non deve rompere riferimenti che si affidano al
 * codice stabile (es. categorie di sistema usate come default nei parser). */
export function useUpdateCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...input }: UpdateCategoryInput) => api.patch<Category>(`/categories/${id}`, input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: categoriesKey }),
  });
}

/** Il backend risponde 409 se la categoria e' ancora referenziata da
 * transazioni o sotto-categorie — il chiamante mostra friendlyErrorMessage
 * dell'ApiError risultante invece di un errore tecnico generico. */
export function useDeleteCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/categories/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: categoriesKey }),
  });
}
