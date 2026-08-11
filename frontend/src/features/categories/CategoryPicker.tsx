import { forwardRef, useId, useState } from "react";
import type { ChangeEvent, SelectHTMLAttributes } from "react";

import { Select } from "../../components/ui/Select";
import { useCategories } from "./api";
import { buildCategoryOptions } from "./utils";
import { CreateCategoryDialog } from "./CreateCategoryDialog";

const NEW_CATEGORY_VALUE = "__new__";

interface CategoryPickerProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  label?: string;
  error?: string;
  includeEmptyOption?: boolean;
}

/**
 * Select di categorie + scorciatoia "+ Nuova categoria" che apre un mini-form
 * (POST /categories, gia' esistente da M03). Non e' il tree management
 * completo di SPEC_FE §46 (reorder/nesting/edit) — solo la creazione al
 * volo dove serve (correzione transazione, creazione regola), scelta
 * confermata con l'utente per non allargare lo scope di questa slice.
 */
export const CategoryPicker = forwardRef<HTMLSelectElement, CategoryPickerProps>(
  ({ label = "Categoria", error, includeEmptyOption = false, onChange, name, ...rest }, ref) => {
    const { data: categories, isLoading } = useCategories();
    const options = buildCategoryOptions(categories);
    const [dialogOpen, setDialogOpen] = useState(false);
    const selectId = useId();

    const handleChange = (event: ChangeEvent<HTMLSelectElement>) => {
      if (event.target.value === NEW_CATEGORY_VALUE) {
        setDialogOpen(true);
        return;
      }
      onChange?.(event);
    };

    const handleCreated = (categoryId: string) => {
      setDialogOpen(false);
      // onChange si aspetta un ChangeEvent vero: ne costruiamo uno minimo
      // (entrambi i chiamanti leggono solo target.value/target.name — sia
      // l'handler diretto di TransactionDetailDrawer sia quello registrato
      // da React Hook Form in RuleFormDialog).
      const select = document.getElementById(selectId) as HTMLSelectElement | null;
      if (select) select.value = categoryId;
      onChange?.({ target: { value: categoryId, name: name ?? "" } } as ChangeEvent<HTMLSelectElement>);
    };

    return (
      <>
        <Select
          ref={ref}
          id={selectId}
          name={name}
          label={label}
          error={error}
          disabled={isLoading}
          onChange={handleChange}
          {...rest}
        >
          {includeEmptyOption && <option value="">Nessuna categoria</option>}
          {options.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
          <option value={NEW_CATEGORY_VALUE}>+ Nuova categoria…</option>
        </Select>
        <CreateCategoryDialog open={dialogOpen} onClose={() => setDialogOpen(false)} onCreated={handleCreated} />
      </>
    );
  },
);
CategoryPicker.displayName = "CategoryPicker";
