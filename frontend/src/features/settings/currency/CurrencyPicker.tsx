import { forwardRef } from "react";
import { useTranslation } from "react-i18next";

import { Select } from "../../../components/ui/Select";
import { useCurrencies } from "./api";

interface CurrencyPickerProps {
  label?: string;
  error?: string;
  disabled?: boolean;
  name?: string;
  value?: string;
  onChange?: React.ChangeEventHandler<HTMLSelectElement>;
  onBlur?: React.FocusEventHandler<HTMLSelectElement>;
}

/**
 * Sistema di valute: sostituisce il campo testo libero a 3 lettere
 * (AccountFormDialog/AssetFormDialog) con una scelta da elenco — poche
 * decine di valute, un `<select>` nativo basta (a differenza di
 * `CategoryPicker`, che serve un Combobox con ricerca per ~150 categorie).
 */
export const CurrencyPicker = forwardRef<HTMLSelectElement, CurrencyPickerProps>(function CurrencyPicker(
  { label, error, disabled, ...rest },
  ref,
) {
  const { t } = useTranslation("common");
  const { data: currencies, isLoading } = useCurrencies();

  return (
    <Select
      // Le opzioni arrivano in modo asincrono (useCurrencies): un <select>
      // nativo che riceve il valore iniziale (via register()/ref) PRIMA che
      // le sue <option> esistano lo scarta silenziosamente (nessuna opzione
      // corrisponde ancora) e resta sulla prima disponibile una volta
      // popolato — bug reale osservato ("EUR" atteso, "AED" mostrato). La
      // `key` forza un remount non appena i dati arrivano, cosi' il valore
      // iniziale viene riapplicato con le opzioni gia' presenti.
      key={isLoading ? "loading" : "loaded"}
      ref={ref}
      label={label ?? t("fields.currency")}
      error={error}
      disabled={disabled || isLoading}
      {...rest}
    >
      {(currencies ?? []).map((c) => (
        <option key={c.code} value={c.code}>
          {c.code} — {c.name}
        </option>
      ))}
    </Select>
  );
});
