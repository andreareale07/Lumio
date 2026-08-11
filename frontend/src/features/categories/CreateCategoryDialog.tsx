import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { useCategories, useCreateCategory } from "./api";

const schema = z.object({
  name: z.string().min(1, "Inserisci un nome"),
  parent_id: z.string(),
});
type FormValues = z.infer<typeof schema>;

export function CreateCategoryDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (categoryId: string) => void;
}) {
  const { data: categories } = useCategories();
  const createCategory = useCreateCategory();
  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { name: "", parent_id: "" } });

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
      });
      reset();
      onCreated(category.id);
    } catch (error) {
      setFormError(friendlyErrorMessage(error, "Non è stato possibile creare la categoria."));
    }
  };

  return (
    <Dialog open={open} onClose={close} title="Nuova categoria">
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="flex flex-col gap-4">
        <Input label="Nome" error={errors.name?.message} {...register("name")} />
        <Select label="Categoria padre (opzionale)" {...register("parent_id")}>
          <option value="">Nessuna — categoria di primo livello</option>
          {topLevelCategories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </Select>
        {formError && (
          <p role="alert" className="text-sm text-danger">
            {formError}
          </p>
        )}
        <div className="mt-2 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={close}>
            Annulla
          </Button>
          <Button type="submit" loading={isSubmitting}>
            Crea categoria
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
