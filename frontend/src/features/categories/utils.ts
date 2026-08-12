import type { Category } from "../../types/api";

export interface CategoryOption {
  id: string;
  label: string;
}

/** Etichetta gerarchica ("Alimentari › Supermercato") invece di un vero
 * albero navigabile — sufficiente per selezionare una categoria in un form
 * (correzione transazione, creazione regola). Il tree management completo
 * (SPEC_FE §46) vive nella pagina dedicata `/settings/categories`. */
export function buildCategoryOptions(categories: Category[] | undefined): CategoryOption[] {
  if (!categories) return [];
  const byId = new Map(categories.map((c) => [c.id, c]));
  const options = categories
    .filter((c) => c.is_active)
    .map((c) => {
      const parent = c.parent_id ? byId.get(c.parent_id) : undefined;
      return {
        id: c.id,
        label: parent ? `${parent.name} › ${c.name}` : c.name,
        sortKey: `${parent?.sort_order ?? c.sort_order}-${c.sort_order}`,
      };
    });
  options.sort((a, b) => a.sortKey.localeCompare(b.sortKey));
  return options.map(({ id, label }) => ({ id, label }));
}

export function categoryLabel(categories: Category[] | undefined, categoryId: string | null): string {
  if (!categoryId || !categories) return "Non categorizzato";
  const options = buildCategoryOptions(categories);
  return options.find((o) => o.id === categoryId)?.label ?? "Non categorizzato";
}
