import { useMemo, useRef, useState } from "react";
import { Check, Plus, Search, TriangleAlert, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { FloatingPanel } from "../../components/ui/FloatingPanel";
import { formatMoney } from "../../lib/format";
import type { TransactionListSummary } from "../../types/api";
import { useTransactionMerchants } from "./api";

export interface FilterOption {
  value: string;
  label: string;
  /** Numero di movimenti, mostrato a destra (solo dove il dato esiste). */
  count?: number;
}

/** Filtro a selezione multipla (OR sui valori scelti). */
export interface SelectFilter {
  key: string;
  label: string;
  values: string[];
  options: FilterOption[];
  /** `true`: le opzioni arrivano dal server con ricerca (liste troppo lunghe
   * per essere scaricate intere, es. i merchant). `options` e' ignorato. */
  remote?: boolean;
}

/** Filtro attivo senza selettore (es. "Senza merchant", import): solo chip rimovibile. */
export interface StaticFilterChip {
  key: string;
  label: string;
  onRemove: () => void;
}

interface TransactionFilterBarProps {
  searchText: string;
  onSearchTextChange: (value: string) => void;
  selectFilters: SelectFilter[];
  onSetFilterValues: (key: string, values: string[]) => void;
  staticChips: StaticFilterChip[];
  review: { count: number; active: boolean; onToggle: () => void } | null;
  hasAnyFilter: boolean;
  onClearAll: () => void;
  summary: TransactionListSummary | undefined;
}

/** Barra filtri di Movimenti: ricerca, filtri rapidi, un chip per ogni filtro
 * attivo (clic = cambia i valori, X = toglie il filtro), "+ Filtro" per
 * aggiungerne altri, "Azzera filtri" e riepilogo conteggio/saldo. Il periodo
 * resta nel navigatore del Topbar (stesso controllo di ogni altra pagina) ma
 * "Azzera filtri" lo riporta al default. */
export function TransactionFilterBar({
  searchText,
  onSearchTextChange,
  selectFilters,
  onSetFilterValues,
  staticChips,
  review,
  hasAnyFilter,
  onClearAll,
  summary,
}: TransactionFilterBarProps) {
  const { t } = useTranslation("transactions");
  // Pannello aperto: "add" (scelta del tipo di filtro) o la key di un filtro
  // (scelta dei suoi valori). Un solo pannello alla volta.
  const [openPanel, setOpenPanel] = useState<string | null>(null);
  // Un ref STABILE per chiave: `FloatingPanel` ricalcola la posizione quando
  // `anchorRef` cambia identita', quindi un oggetto nuovo a ogni render
  // innescherebbe un ciclo di aggiornamenti.
  const anchors = useRef(new Map<string, { current: HTMLElement | null }>());
  const anchorFor = (key: string) => {
    let ref = anchors.current.get(key);
    if (!ref) {
      ref = { current: null };
      anchors.current.set(key, ref);
    }
    return ref;
  };
  const setAnchor = (key: string) => (node: HTMLElement | null) => {
    anchorFor(key).current = node;
  };

  const active = selectFilters.filter((f) => f.values.length > 0);
  const available = selectFilters.filter((f) => f.values.length === 0);

  const chipLabel = (filter: SelectFilter) => {
    const labels = filter.values.map((v) => filter.options.find((o) => o.value === v)?.label ?? v);
    return labels.length > 1 ? `${labels[0]} +${labels.length - 1}` : (labels[0] ?? "");
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="relative">
        <label htmlFor="transactions-search" className="sr-only">
          {t("page.search.label")}
        </label>
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
          aria-hidden="true"
        />
        <input
          id="transactions-search"
          type="search"
          value={searchText}
          onChange={(event) => onSearchTextChange(event.target.value)}
          placeholder={t("page.search.placeholder")}
          className="w-full rounded-lg border border-border bg-surface py-2 pl-9 pr-3 text-sm text-text placeholder:text-text-muted"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("page.filters.active")}>
        {review && (
          <button
            type="button"
            onClick={review.onToggle}
            aria-pressed={review.active}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
              review.active
                ? "border-warning bg-warning-bg text-text"
                : "border-border bg-surface text-text hover:border-primary"
            }`}
          >
            <TriangleAlert className="h-3 w-3" aria-hidden="true" />
            {t("page.needsReview", { count: review.count })}
          </button>
        )}

        {active.map((filter) => (
          <span
            key={filter.key}
            className="inline-flex items-center overflow-hidden rounded-full border border-primary bg-surface-hover text-xs text-text"
          >
            <button
              type="button"
              ref={setAnchor(filter.key)}
              onClick={() => setOpenPanel(openPanel === filter.key ? null : filter.key)}
              aria-haspopup="listbox"
              aria-expanded={openPanel === filter.key}
              className="py-1 pl-2.5 pr-1.5 hover:underline"
            >
              <span className="text-text-muted">{filter.label}:</span> {chipLabel(filter)}
            </button>
            <button
              type="button"
              onClick={() => onSetFilterValues(filter.key, [])}
              aria-label={t("page.filters.removeFilter", { name: `${filter.label}: ${chipLabel(filter)}` })}
              className="py-1 pl-0.5 pr-2 text-text-muted hover:text-text"
            >
              <X className="h-3 w-3" aria-hidden="true" />
            </button>
          </span>
        ))}

        {staticChips.map((chip) => (
          <button
            key={chip.key}
            type="button"
            onClick={chip.onRemove}
            aria-label={t("page.filters.removeFilter", { name: chip.label })}
            className="inline-flex items-center gap-1 rounded-full border border-primary bg-surface-hover px-2.5 py-1 text-xs text-text hover:underline"
          >
            {chip.label}
            <X className="h-3 w-3 text-text-muted" aria-hidden="true" />
          </button>
        ))}

        {available.length > 0 && (
          <button
            type="button"
            ref={setAnchor("add")}
            onClick={() => setOpenPanel(openPanel === "add" ? null : "add")}
            aria-haspopup="menu"
            aria-expanded={openPanel === "add"}
            className="inline-flex items-center gap-1 rounded-full border border-dashed border-border px-2.5 py-1 text-xs text-text-muted hover:border-primary hover:text-text"
          >
            <Plus className="h-3 w-3" aria-hidden="true" />
            {t("page.filters.add")}
          </button>
        )}

        {hasAnyFilter && (
          <button type="button" onClick={onClearAll} className="text-xs font-medium text-primary hover:underline">
            {t("page.filters.clearAll")}
          </button>
        )}
      </div>

      <FloatingPanel open={openPanel === "add"} anchorRef={anchorFor("add")} onClose={() => setOpenPanel(null)}>
        <ul className="flex min-w-44 flex-col p-1 text-sm" role="menu" aria-label={t("page.filters.addTitle")}>
          {available.map((filter) => (
            <li key={filter.key} role="none">
              <button
                type="button"
                role="menuitem"
                onClick={() => setOpenPanel(filter.key)}
                className="w-full rounded-md px-3 py-1.5 text-left text-text hover:bg-surface-hover"
              >
                {filter.label}
              </button>
            </li>
          ))}
        </ul>
      </FloatingPanel>

      {selectFilters.map((filter) => (
        <FloatingPanel
          key={filter.key}
          open={openPanel === filter.key}
          anchorRef={anchorFor(filter.values.length > 0 ? filter.key : "add")}
          onClose={() => setOpenPanel(null)}
        >
          {filter.remote ? (
            <MerchantPicker
              filter={filter}
              onChange={(values) => onSetFilterValues(filter.key, values)}
              onDone={() => setOpenPanel(null)}
            />
          ) : (
            <StaticPicker
              filter={filter}
              onChange={(values) => onSetFilterValues(filter.key, values)}
              onDone={() => setOpenPanel(null)}
            />
          )}
        </FloatingPanel>
      ))}

      {summary && (
        <p className="text-xs text-text-muted" aria-live="polite">
          {t("page.summary.count", { count: summary.count })}
          {(Number(summary.income) > 0 || Number(summary.expenses) > 0) && (
            <>
              {" · "}
              {t("page.summary.income", { value: formatMoney(summary.income, summary.currency) })}
              {" · "}
              {t("page.summary.expenses", { value: formatMoney(summary.expenses, summary.currency) })}
            </>
          )}
        </p>
      )}
    </div>
  );
}

interface PickerProps {
  filter: SelectFilter;
  onChange: (values: string[]) => void;
  onDone: () => void;
}

function StaticPicker({ filter, onChange, onDone }: PickerProps) {
  const [query, setQuery] = useState("");
  const options = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? filter.options.filter((o) => o.label.toLowerCase().includes(needle)) : filter.options;
  }, [filter.options, query]);
  return (
    <PickerShell
      filter={filter}
      options={options}
      query={query}
      onQueryChange={setQuery}
      onChange={onChange}
      onDone={onDone}
      // Con pochi valori la ricerca e' rumore: compare solo per le liste lunghe.
      showSearch={filter.options.length > 6}
    />
  );
}

function MerchantPicker({ filter, onChange, onDone }: PickerProps) {
  const { t } = useTranslation("transactions");
  const [query, setQuery] = useState("");
  const merchants = useTransactionMerchants(query);
  const options: FilterOption[] = (merchants.data?.items ?? []).map((m) => ({
    value: m.merchant,
    label: m.merchant,
    count: m.count,
  }));
  // I valori gia' scelti ma fuori dai risultati correnti restano visibili.
  for (const value of filter.values) {
    if (!options.some((o) => o.value === value)) options.unshift({ value, label: value });
  }
  const total = merchants.data?.total ?? 0;
  const shown = merchants.data?.items.length ?? 0;
  return (
    <PickerShell
      filter={filter}
      options={options}
      query={query}
      onQueryChange={setQuery}
      onChange={onChange}
      onDone={onDone}
      showSearch
      heading={query.trim() ? undefined : t("page.filters.mostFrequent")}
      hint={total > shown ? t("page.filters.merchantsHint", { shown, total }) : undefined}
      isLoading={merchants.isLoading}
    />
  );
}

function PickerShell({
  filter,
  options,
  query,
  onQueryChange,
  onChange,
  onDone,
  showSearch,
  heading,
  hint,
  isLoading,
}: {
  filter: SelectFilter;
  options: FilterOption[];
  query: string;
  onQueryChange: (value: string) => void;
  onChange: (values: string[]) => void;
  onDone: () => void;
  showSearch: boolean;
  heading?: string;
  hint?: string;
  isLoading?: boolean;
}) {
  const { t } = useTranslation("transactions");
  const toggle = (value: string) =>
    onChange(filter.values.includes(value) ? filter.values.filter((v) => v !== value) : [...filter.values, value]);
  const searchLabel = t("page.filters.pickerSearch", { name: filter.label.toLowerCase() });

  return (
    <div className="flex w-72 flex-col">
      {showSearch && (
        <div className="border-b border-border p-2">
          <input
            autoFocus
            type="search"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder={searchLabel}
            aria-label={searchLabel}
            className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-text placeholder:text-text-muted"
          />
        </div>
      )}
      <ul role="listbox" aria-label={filter.label} aria-multiselectable="true" className="max-h-64 overflow-y-auto p-1">
        {heading && <li className="px-3 pb-1 pt-2 text-xs text-text-muted">{heading}</li>}
        {!isLoading && options.length === 0 && (
          <li className="px-3 py-2 text-sm text-text-muted">{t("page.filters.pickerEmpty")}</li>
        )}
        {options.map((option) => {
          const selected = filter.values.includes(option.value);
          return (
            <li key={option.value} role="option" aria-selected={selected}>
              <button
                type="button"
                onClick={() => toggle(option.value)}
                className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-sm text-text hover:bg-surface-hover"
              >
                <span
                  aria-hidden="true"
                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                    selected ? "border-primary bg-primary text-primary-contrast" : "border-border"
                  }`}
                >
                  {selected && <Check className="h-3 w-3" />}
                </span>
                <span className="flex-1 truncate">{option.label}</span>
                {option.count !== undefined && <span className="text-xs text-text-muted">{option.count}</span>}
              </button>
            </li>
          );
        })}
        {hint && <li className="px-3 py-2 text-xs text-text-muted">{hint}</li>}
      </ul>
      <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-text-muted">
        <span>{t("page.filters.selectedCount", { count: filter.values.length })}</span>
        <span className="flex items-center gap-3">
          {filter.values.length > 0 && (
            <button type="button" onClick={() => onChange([])} className="text-primary hover:underline">
              {t("page.filters.deselect")}
            </button>
          )}
          <button type="button" onClick={onDone} className="font-medium text-primary hover:underline">
            {t("page.filters.done")}
          </button>
        </span>
      </div>
    </div>
  );
}
