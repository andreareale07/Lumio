import { forwardRef, useEffect, useId, useImperativeHandle, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Check, ChevronDown, Search } from "lucide-react";

export interface ComboboxOption {
  value: string;
  label: string;
  /** Intestazione sotto cui raggruppare l'opzione (es. il nome della
   * categoria padre) — le opzioni senza `group` finiscono in cima, non
   * raggruppate. */
  group?: string;
  /** Testo secondario mostrato sotto la label nel popover (es. un
   * suggerimento sul tipo di spesa che ci rientra) — mai nel trigger
   * chiuso, solo per aiutare la scelta mentre si sfoglia. */
  hint?: string;
}

interface ComboboxProps {
  label?: string;
  error?: string;
  disabled?: boolean;
  value: string;
  onChange: (value: string) => void;
  /** Riceve il valore CORRENTE (non quello del prop `value`, che un
   * chiamante "non controllato" — es. `register()` di react-hook-form,
   * che non ripassa mai `value` indietro — non aggiorna mai). Bug reale:
   * chiamarlo senza argomenti o con `value` faceva leggere a
   * react-hook-form una stringa vuota stantia, sovrascrivendo la
   * selezione appena fatta (onChange e onBlur condividono lo stesso
   * dispatcher interno in react-hook-form, distinto solo da `event.type`). */
  onBlur?: (currentValue: string) => void;
  options: ComboboxOption[];
  placeholder?: string;
  emptyOptionLabel?: string;
  searchPlaceholder?: string;
  /** Slot fisso in fondo al popover (es. "+ Nuova categoria"), sempre
   * visibile indipendentemente dal filtro di ricerca. */
  footer?: ReactNode;
}

/**
 * Trigger + popover con ricerca, pensato per un elenco troppo lungo per un
 * `<select>` nativo (rework tassonomia: da ~14 a ~150 categorie). Non un
 * elemento form nativo: il valore si propaga chiamando `onChange` con la
 * stringa scelta, stesso principio del "ChangeEvent finto" gia' in uso in
 * `CategoryPicker.tsx` per compatibilita' con `register()` di
 * react-hook-form senza richiedere `Controller` — qui e' il caso comune,
 * non un'eccezione da giustificare. Il ref inoltrato punta al bottone
 * trigger (non a un vero `<select>`): basta perche' react-hook-form possa
 * ancora chiamarci `.focus()` alla validazione fallita, unico uso che fa
 * del ref su un campo non nativo come questo.
 */
export const Combobox = forwardRef<HTMLButtonElement, ComboboxProps>(function Combobox(
  {
    label,
    error,
    disabled,
    value,
    onChange,
    onBlur,
    options,
    placeholder,
    emptyOptionLabel,
    searchPlaceholder,
    footer,
  },
  forwardedRef,
) {
  const { t } = useTranslation("common");
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlighted, setHighlighted] = useState(0);
  // Stato interno, non solo il prop `value`: un consumatore "non
  // controllato" (register() di react-hook-form) non ripassa mai il
  // valore scelto indietro come prop — senza uno stato proprio il trigger
  // continuerebbe a mostrare il placeholder anche dopo una selezione
  // riuscita (bug reale, scoperto dai test). Sincronizzato dal prop quando
  // QUELLO cambia genuinamente (uso controllato, es. TransactionDetailDrawer).
  const [internalValue, setInternalValue] = useState(value);
  useEffect(() => {
    setInternalValue(value);
  }, [value]);
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  useImperativeHandle(forwardedRef, () => triggerRef.current as HTMLButtonElement);
  const listId = useId();
  const triggerId = useId();

  const allOptions = useMemo<ComboboxOption[]>(
    () => (emptyOptionLabel ? [{ value: "", label: emptyOptionLabel }, ...options] : options),
    [options, emptyOptionLabel],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return allOptions;
    return allOptions.filter(
      (o) => o.label.toLowerCase().includes(q) || o.group?.toLowerCase().includes(q) || o.hint?.toLowerCase().includes(q),
    );
  }, [allOptions, query]);

  const selected = allOptions.find((o) => o.value === internalValue);
  // La cleanup dell'effect sotto chiude su `internalValue` al momento in cui
  // l'effect e' partito (quando `open` e' diventato true) — se la selezione
  // e' cambiata nel frattempo (proprio il caso normale: si seleziona, poi
  // il popover si chiude), quella chiusura leggerebbe il valore VECCHIO.
  // Un ref sempre aggiornato evita di dover ri-registrare l'intero effect
  // (con relativo re-focus della ricerca) solo per tenere il valore fresco.
  const internalValueRef = useRef(internalValue);
  internalValueRef.current = internalValue;

  useEffect(() => {
    if (!open) return undefined;
    setQuery("");
    setHighlighted(0);
    const timer = setTimeout(() => searchInputRef.current?.focus(), 0);

    const onMouseDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
      // Il popover si e' appena chiuso (selezione, Escape o click fuori):
      // e' il momento equivalente a un "blur" per un campo non nativo come
      // questo — react-hook-form lo usa per marcare il campo come "toccato".
      onBlur?.(internalValueRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onBlur intenzionalmente non tra le dipendenze: rieseguire l'effect ad ogni render di un onBlur ricreato riaprirebbe il focus sulla ricerca
  }, [open]);

  const select = (optionValue: string) => {
    setInternalValue(optionValue);
    onChange(optionValue);
    setOpen(false);
  };

  const onSearchKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((i) => Math.min(i + 1, filtered.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const option = filtered[highlighted];
      if (option) select(option.value);
    }
  };

  // Raggruppa preservando l'ordine di prima comparsa dei gruppi (gia'
  // ordinati a monte da chi costruisce `options`, es. per sort_order).
  const groups: { name: string | null; options: ComboboxOption[] }[] = [];
  for (const option of filtered) {
    const groupName = option.group ?? null;
    const last = groups[groups.length - 1];
    if (last && last.name === groupName) last.options.push(option);
    else groups.push({ name: groupName, options: [option] });
  }

  return (
    <div className="flex flex-col gap-1.5" ref={containerRef}>
      {label && (
        <label htmlFor={triggerId} className="text-sm font-medium text-text">
          {label}
        </label>
      )}
      <div className="relative">
        <button
          ref={triggerRef}
          type="button"
          id={triggerId}
          disabled={disabled}
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className={`flex h-10 w-full items-center justify-between gap-2 rounded-lg border bg-surface px-3 text-left text-sm text-text disabled:opacity-50 ${
            error ? "border-danger" : "border-border"
          }`}
        >
          <span className={selected ? "truncate text-text" : "truncate text-text-muted"}>
            {selected ? selected.label : placeholder ?? t("select.placeholder")}
          </span>
          <ChevronDown className="h-4 w-4 shrink-0 text-text-muted" aria-hidden="true" />
        </button>

        {open && (
          <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-lg border border-border bg-surface shadow-lg">
            <div className="flex items-center gap-2 border-b border-border px-3 py-2">
              <Search className="h-4 w-4 shrink-0 text-text-muted" aria-hidden="true" />
              <input
                ref={searchInputRef}
                role="combobox"
                aria-expanded={open}
                aria-controls={listId}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setHighlighted(0);
                }}
                onKeyDown={onSearchKeyDown}
                placeholder={searchPlaceholder ?? t("select.searchPlaceholder")}
                className="w-full bg-transparent text-sm text-text placeholder:text-text-muted focus:outline-none"
              />
            </div>

            <ul id={listId} role="listbox" className="max-h-64 overflow-y-auto py-1">
              {filtered.length === 0 && <li className="px-3 py-2 text-sm text-text-muted">Nessun risultato.</li>}
              {groups.map((group, groupIndex) => (
                <li key={group.name ?? `_ungrouped_${groupIndex}`}>
                  {group.name && (
                    <div className="px-3 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
                      {group.name}
                    </div>
                  )}
                  <ul>
                    {group.options.map((option) => {
                      const flatIndex = filtered.indexOf(option);
                      const isHighlighted = flatIndex === highlighted;
                      const isSelected = option.value === internalValue;
                      return (
                        <li key={option.value || "_empty_"}>
                          <button
                            type="button"
                            role="option"
                            aria-selected={isSelected}
                            onMouseEnter={() => setHighlighted(flatIndex)}
                            onClick={() => select(option.value)}
                            className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm ${
                              isHighlighted ? "bg-surface-hover" : ""
                            } ${isSelected ? "text-primary" : "text-text"}`}
                          >
                            <span className="flex flex-col">
                              <span>{option.label}</span>
                              {option.hint && <span className="text-xs text-text-muted">{option.hint}</span>}
                            </span>
                            {isSelected && <Check className="h-4 w-4 shrink-0" aria-hidden="true" />}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>

            {footer && <div className="border-t border-border">{footer}</div>}
          </div>
        )}
      </div>
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
});
