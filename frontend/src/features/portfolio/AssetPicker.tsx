import { forwardRef } from "react";
import type { ChangeEvent } from "react";
import { useTranslation } from "react-i18next";

import { Combobox } from "../../components/ui/Combobox";
import type { ComboboxOption } from "../../components/ui/Combobox";
import { useAssets } from "./api";
import { useAssetTypeLabel } from "./labels";

interface AssetPickerProps {
  label?: string;
  error?: string;
  disabled?: boolean;
  name?: string;
  value?: string;
  includeEmptyOption?: boolean;
  // Il significato di "nessun valore" cambia col contesto: "Tutti i
  // titoli" in un filtro, "Nessun titolo" in un form — mai un'unica
  // etichetta fissa per entrambi i casi (a differenza di CategoryPicker,
  // dove "Nessuna categoria" ha senso in entrambi).
  emptyOptionLabel?: string;
  onChange?: (event: ChangeEvent<HTMLSelectElement>) => void;
  // Vedi CategoryPicker.tsx per la stessa scelta: deve restare assegnabile
  // sia da register() di react-hook-form sia da un onBlur controllato a mano.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any -- deve restare assegnabile da ChangeHandler di react-hook-form
  onBlur?: (event?: any) => void;
}

/**
 * Combobox con ricerca per scegliere UN asset da tutto il workspace —
 * sostituisce una `<select>` nativa che diventa inusabile quando un utente
 * attivo ha accumulato decine/centinaia di titoli nel tempo (stesso
 * problema gia' risolto una volta per le categorie, `CategoryPicker.tsx`:
 * "inusabile con ~150 opzioni piatte"). Stessa interfaccia esterna "alla
 * select" (`value`/`onChange` con un ChangeEvent, `ref`/`onBlur` inoltrati)
 * per restare compatibile sia con `register()` di react-hook-form
 * (`InvestmentTransactionFormDialog`) sia con l'uso controllato diretto nei
 * filtri (`TaxRealizedEventsPage`, `RealizedPositionsPage`).
 */
export const AssetPicker = forwardRef<HTMLButtonElement, AssetPickerProps>(function AssetPicker(
  { label, error, disabled, name, value = "", includeEmptyOption = false, emptyOptionLabel, onChange, onBlur },
  ref,
) {
  const { t } = useTranslation("portfolio");
  const assetTypeLabel = useAssetTypeLabel();
  const { data: assets, isLoading } = useAssets();

  const options: ComboboxOption[] = (assets ?? []).map((asset) => {
    // Stessa precedenza di AssetDetailPage.tsx ("display_name ?? name"),
    // estesa con symbol in mezzo: il nome ripulito dal provider (es.
    // "WisdomTree Gold 3x Daily Levera") e' quello che l'utente riconosce e
    // cerca, mai il nome grezzo del parser (es. "WITR MU.AS.I.GOLD
    // ETP2062") che finiva per essere l'unico testo cercabile (bug reale:
    // cercare "wisdom" non trovava nulla). Il nome tecnico non sparisce,
    // resta nell'hint — cercabile anche lui, solo non piu' l'unica via.
    const label = asset.display_name ?? asset.symbol ?? asset.name;
    const technicalBits = [asset.symbol, asset.name].filter((bit) => bit && bit !== label);
    const hint = [...technicalBits, assetTypeLabel(asset.asset_type)].join(" · ");
    return { value: asset.id, label, hint };
  });

  const emitChange = (nextValue: string) => {
    onChange?.({ target: { value: nextValue, name: name ?? "" } } as ChangeEvent<HTMLSelectElement>);
  };

  const emitBlur = (currentValue: string) => {
    onBlur?.({ target: { value: currentValue, name: name ?? "" } });
  };

  return (
    <Combobox
      ref={ref}
      label={label ?? t("assetPicker.defaultLabel")}
      error={error}
      disabled={disabled || isLoading}
      value={value}
      onChange={emitChange}
      onBlur={emitBlur}
      options={options}
      emptyOptionLabel={includeEmptyOption ? (emptyOptionLabel ?? t("assetPicker.emptyOption")) : undefined}
      placeholder={t("assetPicker.placeholder")}
      searchPlaceholder={t("assetPicker.searchPlaceholder")}
    />
  );
});
