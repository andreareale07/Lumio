import { useMemo, useState } from "react";
import { FolderTree, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Input } from "../../components/ui/Input";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import type { Category, CategoryKind } from "../../types/api";
import { useCategories, useDeleteCategory, useUpdateCategory } from "./api";
import { categoryKindLabel } from "./utils";
import { CategoryFormDialog } from "./CategoryFormDialog";

const KIND_ORDER: CategoryKind[] = ["expense", "income", "transfer", "investment", "neutral"];

/** Milestone 06.5 (audit retroattivo) + rework tassonomia: gestione completa
 * delle categorie. Da ~14 a ~145 categorie ha reso necessario due cose che
 * la versione precedente non aveva: raggruppamento per `kind` (altrimenti
 * 23 padri in un'unica lista piatta) e una ricerca (per trovarne una
 * specifica senza scorrere tutto). Le categorie di sistema restano sempre
 * di sola lettura — il backend le protegge gia' con un 403, la UI evita di
 * mostrare azioni che fallirebbero comunque. */
export function CategoriesSettingsPage() {
  const { t } = useTranslation(["settings", "common"]);
  const { data: categories, isLoading, isError, refetch } = useCategories();
  const [formCategory, setFormCategory] = useState<Category | null | "new">(null);
  const [categoryToDelete, setCategoryToDelete] = useState<Category | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const updateCategory = useUpdateCategory();
  const deleteCategory = useDeleteCategory();

  const childrenOf = (parentId: string) => (categories ?? []).filter((c) => c.parent_id === parentId);

  const trimmedQuery = query.trim().toLowerCase();
  const isSearching = trimmedQuery.length > 0;
  // Con la ricerca attiva, l'elenco filtrato torna PIATTO (nessun figlio
  // nascosto dentro un <details> chiuso): l'utente sta cercando qualcosa di
  // specifico, non ha senso fargli comunque espandere il padre a mano.
  const searchMatches = isSearching
    ? (categories ?? []).filter(
        (c) => c.name.toLowerCase().includes(trimmedQuery) || c.code.toLowerCase().includes(trimmedQuery),
      )
    : [];

  const byKind = useMemo(() => {
    const map = new Map<CategoryKind, Category[]>();
    for (const kind of KIND_ORDER) map.set(kind, []);
    for (const category of categories ?? []) {
      if (category.parent_id) continue; // solo le radici qui, i figli via childrenOf
      map.get(category.kind)?.push(category);
    }
    return map;
  }, [categories]);

  const onConfirmDelete = async () => {
    if (!categoryToDelete) return;
    setDeleteError(null);
    try {
      await deleteCategory.mutateAsync(categoryToDelete.id);
      setCategoryToDelete(null);
    } catch (error) {
      setDeleteError(friendlyErrorMessage(error, t("items.categories.page.deleteDialog.error")));
    }
  };

  const rowProps = (category: Category) => ({
    category,
    onEdit: () => setFormCategory(category),
    onDelete: () => {
      setDeleteError(null);
      setCategoryToDelete(category);
    },
    onToggleActive: () => updateCategory.mutate({ id: category.id, is_active: !category.is_active }),
  });

  const totalCount = categories?.length ?? 0;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-text">{t("items.categories.label")}</h1>
          <p className="text-sm text-text-muted">{t("items.categories.pageDescription")}</p>
        </div>
        <Button size="sm" onClick={() => setFormCategory("new")}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t("items.categories.page.newCategory")}
        </Button>
      </div>

      {totalCount > 0 && (
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("items.categories.page.searchPlaceholder", { count: totalCount })}
          aria-label={t("items.categories.page.searchAriaLabel")}
        />
      )}

      {isLoading && <SkeletonRows rows={4} />}
      {isError && <ErrorState message={t("items.categories.page.loadError")} onRetry={() => void refetch()} />}

      {!isLoading && !isError && totalCount === 0 && (
        <EmptyState
          icon={FolderTree}
          title={t("items.categories.page.empty.title")}
          description={t("items.categories.page.empty.description")}
          action={<Button onClick={() => setFormCategory("new")}>{t("items.categories.page.empty.action")}</Button>}
        />
      )}

      {!isLoading && !isError && isSearching && (
        <div className="flex flex-col gap-2">
          {searchMatches.length === 0 && (
            <p className="text-sm text-text-muted">{t("items.categories.page.noSearchResults", { query })}</p>
          )}
          {searchMatches.map((category) => (
            <CategoryRow key={category.id} {...rowProps(category)} />
          ))}
        </div>
      )}

      {!isLoading && !isError && !isSearching && totalCount > 0 && (
        <div className="flex flex-col gap-5">
          {KIND_ORDER.filter((kind) => (byKind.get(kind) ?? []).length > 0).map((kind) => (
            <section key={kind} className="flex flex-col gap-2">
              <h2 className="text-sm font-semibold text-text-muted">{categoryKindLabel(t, kind)}</h2>
              {(byKind.get(kind) ?? []).map((root) => {
                const children = childrenOf(root.id);
                return (
                  <div key={root.id} className="flex flex-col gap-2">
                    <CategoryRow {...rowProps(root)} />
                    {children.length > 0 && (
                      <details className="ml-6">
                        <summary className="cursor-pointer text-sm text-text-muted select-none">
                          {t("items.categories.page.subcategories", { count: children.length })}
                        </summary>
                        <div className="mt-2 flex flex-col gap-2">
                          {children.map((child) => (
                            <CategoryRow key={child.id} {...rowProps(child)} />
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                );
              })}
            </section>
          ))}
        </div>
      )}

      <CategoryFormDialog
        open={formCategory !== null}
        onClose={() => setFormCategory(null)}
        category={formCategory === "new" ? null : formCategory}
      />

      <Dialog
        open={!!categoryToDelete}
        onClose={() => setCategoryToDelete(null)}
        title={t("items.categories.page.deleteDialog.title")}
      >
        <p className="text-sm text-text-muted">
          {t("items.categories.page.deleteDialog.body", { name: categoryToDelete?.name })}
        </p>
        {deleteError && (
          <p role="alert" className="mt-2 text-sm text-danger">
            {deleteError}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setCategoryToDelete(null)}>
            {t("common:actions.cancel")}
          </Button>
          <Button variant="danger" loading={deleteCategory.isPending} onClick={() => void onConfirmDelete()}>
            {t("items.categories.page.row.delete")}
          </Button>
        </div>
      </Dialog>
    </div>
  );
}

function CategoryRow({
  category,
  onEdit,
  onDelete,
  onToggleActive,
}: {
  category: Category;
  onEdit: () => void;
  onDelete: () => void;
  onToggleActive: () => void;
}) {
  const { t } = useTranslation("settings");
  return (
    <Card className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <p className="font-medium text-text">{category.name}</p>
        <p className="text-xs text-text-muted">{category.code}</p>
      </div>
      <div className="flex items-center gap-2">
        {category.is_system && <Badge tone="neutral">{t("items.categories.page.row.badgeSystem")}</Badge>}
        {!category.is_active && <Badge tone="neutral">{t("items.categories.page.row.badgeInactive")}</Badge>}
        {!category.is_system && (
          <>
            <Button variant="ghost" size="sm" onClick={onToggleActive}>
              {t(category.is_active ? "items.categories.page.row.toggleDeactivate" : "items.categories.page.row.toggleActivate")}
            </Button>
            <Button variant="ghost" size="sm" onClick={onEdit}>
              {t("items.categories.page.row.edit")}
            </Button>
            <Button variant="ghost" size="sm" onClick={onDelete}>
              {t("items.categories.page.row.delete")}
            </Button>
          </>
        )}
      </div>
    </Card>
  );
}
