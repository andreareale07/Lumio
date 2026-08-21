import { useState } from "react";
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
import { CATEGORY_KINDS } from "../../types/api";
import { useCategories, useCreateCategory } from "./api";
import { categoryKindLabel } from "./utils";

function buildSchema(t: TFunction) {
  return z.object({
    name: z.string().min(1, t("validation.name")),
    parent_id: z.string(),
    kind: z.enum(CATEGORY_KINDS),
  });
}
type FormValues = z.infer<ReturnType<typeof buildSchema>>;

export function CreateCategoryDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (categoryId: string) => void;
}) {
  const { t } = useTranslation(["categories", "common"]);
  const { data: categories } = useCategories();
  const createCategory = useCreateCategory();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(buildSchema(t)),
    defaultValues: { name: "", parent_id: "", kind: "expense" },
  });
  // Come in CategoryFormDialog: il kind si eredita dal padre su una
  // sottocategoria, editabile solo creando una categoria di primo livello.
  const isRoot = !watch("parent_id");

  // Solo le categorie di primo livello come possibile padre (SPEC_FE §46 non
  // richiede in questa scorciatoia una gerarchia arbitrariamente profonda).
  const topLevelCategories = (categories ?? []).filter((c) => !c.parent_id && c.is_active);

  const close = () => {
    reset();
    setFormError(null);
    onClose();
  };

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      const category = await createCategory.mutateAsync({
        name: values.name,
        parent_id: values.parent_id || null,
        kind: values.parent_id ? undefined : values.kind,
      });
      reset();
      onCreated(category.id);
    } catch (error) {
      setFormError(friendlyErrorMessage(error, t("createDialog.error")));
    }
  };

  return (
    <Dialog open={open} onClose={close} title={t("createDialog.title")}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Input label={t("fields.name")} error={errors.name?.message} {...register("name")} />
        <Select label={t("fields.parent")} {...register("parent_id")}>
          <option value="">{t("noParentOption")}</option>
          {topLevelCategories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </Select>
        {isRoot && (
          <Select label={t("fields.kind")} error={errors.kind?.message} {...register("kind")}>
            {CATEGORY_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {categoryKindLabel(t, kind)}
              </option>
            ))}
          </Select>
        )}
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
            {t("createDialog.submit")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
