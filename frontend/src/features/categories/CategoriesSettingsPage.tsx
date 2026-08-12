import { useState } from "react";
import { FolderTree, Plus } from "lucide-react";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import type { Category } from "../../types/api";
import { useCategories, useDeleteCategory, useUpdateCategory } from "./api";
import { CategoryFormDialog } from "./CategoryFormDialog";

/** Milestone 06.5 (audit retroattivo): gestione completa delle categorie —
 * fino a qui il frontend copriva solo la creazione al volo (CategoryPicker),
 * nonostante il backend esponesse gia' da M03 modifica/eliminazione/ordine.
 * Le categorie di sistema (is_system, workspace_id nullo, condivise da ogni
 * workspace) sono sempre di sola lettura qui — il backend le protegge gia'
 * con un 403, la UI evita di mostrare azioni che fallirebbero comunque. */
export function CategoriesSettingsPage() {
  const { data: categories, isLoading, isError, refetch } = useCategories();
  const [formCategory, setFormCategory] = useState<Category | null | "new">(null);
  const [categoryToDelete, setCategoryToDelete] = useState<Category | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const updateCategory = useUpdateCategory();
  const deleteCategory = useDeleteCategory();

  const topLevel = (categories ?? []).filter((c) => !c.parent_id);
  const childrenOf = (parentId: string) => (categories ?? []).filter((c) => c.parent_id === parentId);

  const onConfirmDelete = async () => {
    if (!categoryToDelete) return;
    setDeleteError(null);
    try {
      await deleteCategory.mutateAsync(categoryToDelete.id);
      setCategoryToDelete(null);
    } catch (error) {
      setDeleteError(friendlyErrorMessage(error, "Non è stato possibile eliminare la categoria."));
    }
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h1 className="text-lg font-semibold text-text">Categorie</h1>
          <p className="text-sm text-text-muted">
            Le categorie di sistema sono condivise e non modificabili. Quelle create da te possono essere
            rinominate, riordinate, disattivate o eliminate se non più in uso.
          </p>
        </div>
        <Button size="sm" onClick={() => setFormCategory("new")}>
          <Plus className="h-4 w-4" aria-hidden="true" />
          Nuova
        </Button>
      </div>

      {isLoading && <SkeletonRows rows={4} />}
      {isError && <ErrorState message="Non siamo riusciti a caricare le categorie." onRetry={() => void refetch()} />}

      {!isLoading && !isError && topLevel.length === 0 && (
        <EmptyState
          icon={FolderTree}
          title="Nessuna categoria"
          description="Crea la tua prima categoria personalizzata."
          action={<Button onClick={() => setFormCategory("new")}>Nuova categoria</Button>}
        />
      )}

      {!isLoading && !isError && topLevel.length > 0 && (
        <div className="flex flex-col gap-2">
          {topLevel.map((category) => (
            <div key={category.id} className="flex flex-col gap-2">
              <CategoryRow
                category={category}
                onEdit={() => setFormCategory(category)}
                onDelete={() => {
                  setDeleteError(null);
                  setCategoryToDelete(category);
                }}
                onToggleActive={() =>
                  updateCategory.mutate({ id: category.id, is_active: !category.is_active })
                }
              />
              {childrenOf(category.id).map((child) => (
                <div key={child.id} className="ml-6">
                  <CategoryRow
                    category={child}
                    onEdit={() => setFormCategory(child)}
                    onDelete={() => {
                      setDeleteError(null);
                      setCategoryToDelete(child);
                    }}
                    onToggleActive={() => updateCategory.mutate({ id: child.id, is_active: !child.is_active })}
                  />
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      <CategoryFormDialog
        open={formCategory !== null}
        onClose={() => setFormCategory(null)}
        category={formCategory === "new" ? null : formCategory}
      />

      <Dialog open={!!categoryToDelete} onClose={() => setCategoryToDelete(null)} title="Eliminare la categoria?">
        <p className="text-sm text-text-muted">
          "{categoryToDelete?.name}" verrà eliminata definitivamente. Se è ancora usata da qualche transazione o
          sotto-categoria, l'eliminazione verrà rifiutata: in quel caso puoi disattivarla invece.
        </p>
        {deleteError && (
          <p role="alert" className="mt-2 text-sm text-danger">
            {deleteError}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setCategoryToDelete(null)}>
            Annulla
          </Button>
          <Button variant="danger" loading={deleteCategory.isPending} onClick={() => void onConfirmDelete()}>
            Elimina
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
  return (
    <Card className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <p className="font-medium text-text">{category.name}</p>
        <p className="text-xs text-text-muted">{category.code}</p>
      </div>
      <div className="flex items-center gap-2">
        {category.is_system && <Badge tone="neutral">Sistema</Badge>}
        {!category.is_active && <Badge tone="neutral">Disattiva</Badge>}
        {!category.is_system && (
          <>
            <Button variant="ghost" size="sm" onClick={onToggleActive}>
              {category.is_active ? "Disattiva" : "Attiva"}
            </Button>
            <Button variant="ghost" size="sm" onClick={onEdit}>
              Modifica
            </Button>
            <Button variant="ghost" size="sm" onClick={onDelete}>
              Elimina
            </Button>
          </>
        )}
      </div>
    </Card>
  );
}
