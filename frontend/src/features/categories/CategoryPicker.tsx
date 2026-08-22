import { forwardRef, useState } from "react";
import type { ChangeEvent } from "react";
import { Plus } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Combobox } from "../../components/ui/Combobox";
import { useCategories } from "./api";
import { buildCategoryComboboxOptions } from "./utils";
import { CreateCategoryDialog } from "./CreateCategoryDialog";

interface CategoryPickerProps {
  label?: string;
  error?: string;
  disabled?: boolean;
  name?: string;
  value?: string;
  includeEmptyOption?: boolean;
  onChange?: (event: ChangeEvent<HTMLSelectElement>) => void;
  // Tipizzato largo (non `() => void`) per restare assegnabile anche
  // quando arriva da `register()` di react-hook-form, il cui `onBlur` si
  // aspetta un vero evento — qui viene comunque invocato senza argomenti
  // (il Combobox non e' un elemento nativo, non ne genera uno reale).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- deve restare assegnabile da ChangeHandler di react-hook-form
  onBlur?: (event?: any) => void;
}

/**
 * Combobox di categorie + scorciatoia "+ Nuova categoria" che apre un
 * mini-form (POST /categories, gia' esistente da M03) per la creazione al
 * volo dove serve (correzione transazione, creazione regola). Rework
 * tassonomia: sostituisce il precedente `<select>` nativo, inusabile con
 * ~150 opzioni piatte — l'interfaccia esterna resta pero' quella di un
 * campo controllato "alla select" (`value`/`onChange` con un ChangeEvent,
 * `ref`/`onBlur` inoltrati) per restare compatibile sia con `register()` di
 * react-hook-form sia con l'uso controllato diretto, senza toccare i
 * chiamanti esistenti.
 *
 * La gestione completa (modifica/eliminazione/ordine, SPEC_FE §46) vive
 * nella pagina dedicata `/settings/categories` (CategoriesSettingsPage).
 */
export const CategoryPicker = forwardRef<HTMLButtonElement, CategoryPickerProps>(function CategoryPicker(
  { label, error, disabled, name, value = "", includeEmptyOption = false, onChange, onBlur },
  ref,
) {
  const { t } = useTranslation("categories");
  const { data: categories, isLoading } = useCategories();
  const options = buildCategoryComboboxOptions(categories, t);
  const [dialogOpen, setDialogOpen] = useState(false);

  const emitChange = (nextValue: string) => {
    onChange?.({ target: { value: nextValue, name: name ?? "" } } as ChangeEvent<HTMLSelectElement>);
  };

  // `onBlur` di react-hook-form (via register()) condivide lo stesso
  // dispatcher interno di `onChange` (distinto solo da `event.type`): un
  // `event.target.value` stantio qui sovrascriverebbe silenziosamente la
  // selezione appena fatta (bug reale, trovato dai test) — per questo il
  // Combobox passa il valore CORRENTE, non il prop `value` (che un
  // consumatore "non controllato" come register() non ripassa mai).
  const emitBlur = (currentValue: string) => {
    onBlur?.({ target: { value: currentValue, name: name ?? "" } });
  };

  const handleCreated = (categoryId: string) => {
    setDialogOpen(false);
    emitChange(categoryId);
  };

  return (
    <>
      <Combobox
        ref={ref}
        label={label ?? t("picker.defaultLabel")}
        error={error}
        disabled={disabled || isLoading}
        value={value}
        onChange={emitChange}
        onBlur={emitBlur}
        options={options}
        emptyOptionLabel={includeEmptyOption ? t("picker.emptyOption") : undefined}
        placeholder={t("picker.placeholder")}
        searchPlaceholder={t("picker.searchPlaceholder")}
        footer={
          <button
            type="button"
            onClick={() => setDialogOpen(true)}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-medium text-primary hover:bg-surface-hover"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t("picker.newCategoryButton")}
          </button>
        }
      />
      <CreateCategoryDialog open={dialogOpen} onClose={() => setDialogOpen(false)} onCreated={handleCreated} />
    </>
  );
});
