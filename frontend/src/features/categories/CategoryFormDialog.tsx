import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import type { TFunction } from "i18next";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { CATEGORY_KINDS, type Category } from "../../types/api";
import { useCategories, useCreateCategory, useUpdateCategory } from "./api";
import { categoryDisplayName, categoryKindLabel } from "./utils";

function buildSchema(t: TFunction) {
  return z.object({
    name: z.string().min(1, t("validation.name")),
    parent_id: z.string(),
    kind: z.enum(CATEGORY_KINDS),
    sort_order: z.number().int(),
  });
}
type FormValues = z.infer<ReturnType<typeof buildSchema>>;

interface CategoryFormDialogProps {
  open: boolean;
  onClose: () => void;
  /** Se presente, il dialog modifica questa categoria invece di crearne una nuova. */
  category?: Category | null;
}

function valuesFrom(category: Category | null | undefined): FormValues {
  if (category) {
    return {
      name: category.name,
      parent_id: category.parent_id ?? "",
      kind: category.kind,
      sort_order: category.sort_order,
    };
  }
  return { name: "", parent_id: "", kind: "expense", sort_order: 0 };
}

/** Gestione completa (SPEC_FE §46) distinta dalla creazione al volo di
 * CreateCategoryDialog (usata dentro CategoryPicker): qui si modificano
 * anche categorie gia' esistenti (nome, padre, ordine). L'attivazione/
 * disattivazione resta un'azione diretta sulla riga della lista, non un
 * campo di questo form (stesso pattern di RulesPage per is_active). */
export function CategoryFormDialog({ open, onClose, category }: CategoryFormDialogProps) {
  const { t } = useTranslation(["categories", "common"]);
  const { data: categories } = useCategories();
  const createCategory = useCreateCategory();
  const updateCategory = useUpdateCategory();
  const [formError, setFormError] = useState<string | null>(null);
  const isEditing = !!category;

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(buildSchema(t)),
    defaultValues: valuesFrom(category),
  });
  // Il kind si eredita SEMPRE dal padre su una sottocategoria (il backend lo
  // impone comunque, vedi validate_kind_matches_parent): editabile solo
  // scegliendo "nessun padre", altrimenti sarebbe un campo che sembra
  // libero ma che il salvataggio rifiuterebbe silenziosamente se diverso.
  const selectedParentId = watch("parent_id");
  const isRoot = !selectedParentId;

  useEffect(() => {
    if (open) {
      reset(valuesFrom(category));
      setFormError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset intenzionale solo su open/category
  }, [open, category]);

  // Solo categorie di primo livello come padre (stessa scelta di
  // CreateCategoryDialog), escludendo la categoria stessa in modifica.
  const parentOptions = (categories ?? []).filter(
    (c) => c.is_active && !c.parent_id && c.id !== category?.id,
  );

  const close = () => {
    setFormError(null);
    onClose();
  };

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    const payload = {
      name: values.name,
      parent_id: values.parent_id || null,
      // Su una sottocategoria non si invia affatto: il backend lo eredita
      // dal padre da solo, e inviarne uno diverso verrebbe comunque rifiutato.
      kind: values.parent_id ? undefined : values.kind,
      sort_order: values.sort_order,
    };
    try {
      if (isEditing) {
        await updateCategory.mutateAsync({ id: category.id, ...payload });
      } else {
        await createCategory.mutateAsync(payload);
      }
      close();
    } catch (error) {
      setFormError(friendlyErrorMessage(error, t("editDialog.error")));
    }
  };

  return (
    <Dialog open={open} onClose={close} title={isEditing ? t("editDialog.editTitle") : t("editDialog.createTitle")}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Input label={t("fields.name")} error={errors.name?.message} {...register("name")} />
        <Select label={t("fields.parent")} error={errors.parent_id?.message} {...register("parent_id")}>
          <option value="">{t("noParentOption")}</option>
          {parentOptions.map((c) => (
            <option key={c.id} value={c.id}>
              {categoryDisplayName(t, c)}
            </option>
          ))}
        </Select>
        {isRoot ? (
          <Select label={t("fields.kind")} error={errors.kind?.message} {...register("kind")}>
            {CATEGORY_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {categoryKindLabel(t, kind)}
              </option>
            ))}
          </Select>
        ) : (
          <p className="text-sm text-text-muted">{t("kindInheritedNote")}</p>
        )}
        <Input
          label={t("fields.sortOrder")}
          type="number"
          hint={t("sortOrderHint")}
          error={errors.sort_order?.message}
          {...register("sort_order", { valueAsNumber: true })}
        />
        {formError && (
          <p role="alert" className="text-sm text-danger">
            {formError}
          </p>
        )}
        <div className="mt-2 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={close}>
            {t("common:actions.cancel")}
          </Button>
          <Button type="submit" loading={isSubmitting}>
            {isEditing ? t("editDialog.submitEdit") : t("editDialog.submitCreate")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
