import { useRef, useState } from "react";
import type { ReactNode } from "react";
import { Check, Plus, Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useIsDesktop } from "../../lib/useIsDesktop";
import { BottomSheet } from "../ui/BottomSheet";
import { Button } from "../ui/Button";
import { FloatingPanel } from "../ui/FloatingPanel";

export interface FilterOption {
  value: string;
  label: string;
  /** Numero di elementi, mostrato a destra (solo dove il dato esiste). */
  count?: number;
}

/** Risultato di una sorgente di opzioni remota (liste troppo lunghe per
 * essere scaricate intere, es. i merchant). */
export interface RemoteOptions {
  options: FilterOption[];
  /** Totale lato server: se maggiore delle opzioni mostrate compare un invito a cercare. */
  total: number;
  isLoading: boolean;
  /** Intestazione sopra l'elenco quando la ricerca e' vuota (es. "Piu' frequenti"). */
  heading?: string;
}

/** Filtro a selezione multipla (OR sui valori scelti), o singola con `single`. */
export interface SelectFilter {
  key: string;
  label: string;
  values: string[];
  options: FilterOption[];
  /** `true`: le opzioni arrivano dal server con ricerca (`options` e' ignorato). */
  remote?: boolean;
  /** Hook che fornisce le opzioni remote per il testo cercato: va chiamato
   * sempre, da un componente dedicato (mai in modo condizionale). */
  useRemoteOptions?: (query: string) => RemoteOptions;
  /** Un solo valore alla volta: scegliere sostituisce e chiude. */
  single?: boolean;
}

/** Filtro attivo senza selettore (es. "Senza merchant", import): solo chip rimovibile. */
export interface StaticFilterChip {
  key: string;
  label: string;
  onRemove: () => void;
}

/** Filtro rapido a due stati (es. "Da verificare"). */
export interface QuickFilter {
  key: string;
  label: string;
  icon?: ReactNode;
  active: boolean;
  onToggle: () => void;
}

export interface FilterBarProps {
  /** Assente = nessuna ricerca testuale (pagine con soli filtri a valori). */
  search?: { id: string; label: string; placeholder: string; value: string; onChange: (value: string) => void };
  selectFilters: SelectFilter[];
  onSetFilterValues: (key: string, values: string[]) => void;
  staticChips?: StaticFilterChip[];
  quickFilters?: QuickFilter[];
  hasAnyFilter: boolean;
  onClearAll: () => void;
  /** Riga sotto i filtri (conteggio, totali). */
  summary?: ReactNode;
}

// Il chip e' visivamente basso, ma l'area di tocco arriva a ~44px con un
// pseudo-elemento che sporge sopra e sotto (su desktop non serve).
const chipBase =
  "relative inline-flex h-9 items-center rounded-full border text-sm before:absolute before:inset-x-0 before:-inset-y-1 before:content-[''] md:h-7 md:text-xs md:before:hidden";

/** Barra filtri condivisa da tutte le liste (modello deciso con Movimenti):
 * ricerca in cima; sotto una riga con i filtri rapidi, un chip per ogni filtro
 * attivo (tocco = cambia valori, X = toglie), "+ Filtro" per aggiungerne altri e
 * "Azzera filtri"; poi il riepilogo. Su smartphone i pannelli sono bottom sheet
 * con "Azzera" e "Applica" (le scelte si applicano solo all'Applica); su desktop
 * popover con applicazione immediata. */
export function FilterBar({
  search,
  selectFilters,
  onSetFilterValues,
  staticChips = [],
  quickFilters = [],
  hasAnyFilter,
  onClearAll,
  summary,
}: FilterBarProps) {
  const { t } = useTranslation("common");
  const isDesktop = useIsDesktop();
  // Pannello aperto: "add" (scelta del tipo di filtro) o la key di un filtro.
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
  const closePanel = () => setOpenPanel(null);

  const active = selectFilters.filter((f) => f.values.length > 0);
  const available = selectFilters.filter((f) => f.values.length === 0);

  const chipLabel = (filter: SelectFilter) => {
    const labels = filter.values.map((v) => filter.options.find((o) => o.value === v)?.label ?? v);
    return labels.length > 1 ? `${labels[0]} +${labels.length - 1}` : (labels[0] ?? "");
  };

  const openFilter = selectFilters.find((f) => f.key === openPanel) ?? null;
  const addMenu = (
    <ul className="flex min-w-44 flex-col p-1 text-sm" role="menu" aria-label={t("filters.addTitle")}>
      {available.map((filter) => (
        <li key={filter.key} role="none">
          <button
            type="button"
            role="menuitem"
            onClick={() => setOpenPanel(filter.key)}
            className="flex h-11 w-full items-center rounded-md px-3 text-left text-text hover:bg-surface-hover md:h-auto md:py-1.5"
          >
            {filter.label}
          </button>
        </li>
      ))}
    </ul>
  );

  const picker = (filter: SelectFilter, mobile: boolean) => (
    <FilterPicker
      key={`${filter.key}-${mobile ? "m" : "d"}`}
      filter={filter}
      mobile={mobile}
      onApply={(values) => {
        onSetFilterValues(filter.key, values);
        closePanel();
      }}
      onChangeLive={(values) => onSetFilterValues(filter.key, values)}
      onDone={closePanel}
    />
  );

  return (
    <div className="flex flex-col gap-3">
      {search && (
        <div className="relative">
          <label htmlFor={search.id} className="sr-only">
            {search.label}
          </label>
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
            aria-hidden="true"
          />
          <input
            id={search.id}
            type="search"
            value={search.value}
            onChange={(event) => search.onChange(event.target.value)}
            placeholder={search.placeholder}
            className="h-11 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm text-text placeholder:text-text-muted md:h-9"
          />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("filters.active")}>
        {quickFilters.map((quick) => (
          <button
            key={quick.key}
            type="button"
            onClick={quick.onToggle}
            aria-pressed={quick.active}
            className={`${chipBase} gap-1.5 px-3 md:px-2.5 ${
              quick.active
                ? "border-warning bg-warning-bg text-text"
                : "border-border bg-surface text-text hover:border-primary"
            }`}
          >
            {quick.icon}
            {quick.label}
          </button>
        ))}

        {active.map((filter) => (
          <span key={filter.key} className={`${chipBase} border-primary bg-surface-hover text-text`}>
            <button
              type="button"
              ref={setAnchor(filter.key)}
              onClick={() => setOpenPanel(openPanel === filter.key ? null : filter.key)}
              aria-haspopup={isDesktop ? "listbox" : "dialog"}
              aria-expanded={openPanel === filter.key}
              className="h-full max-w-[14rem] truncate rounded-l-full py-1 pl-3 pr-1.5 hover:underline md:pl-2.5"
            >
              <span className="text-text-muted">{filter.label}:</span> {chipLabel(filter)}
            </button>
            <button
              type="button"
              onClick={() => onSetFilterValues(filter.key, [])}
              aria-label={t("filters.removeFilter", { name: `${filter.label}: ${chipLabel(filter)}` })}
              className="flex h-full items-center rounded-r-full pl-1 pr-3 text-text-muted hover:text-text md:pr-2"
            >
              <X className="h-3.5 w-3.5 md:h-3 md:w-3" aria-hidden="true" />
            </button>
          </span>
        ))}

        {staticChips.map((chip) => (
          <button
            key={chip.key}
            type="button"
            onClick={chip.onRemove}
            aria-label={t("filters.removeFilter", { name: chip.label })}
            className={`${chipBase} gap-1.5 border-primary bg-surface-hover px-3 text-text hover:underline md:px-2.5`}
          >
            {chip.label}
            <X className="h-3.5 w-3.5 text-text-muted md:h-3 md:w-3" aria-hidden="true" />
          </button>
        ))}

        {available.length > 0 && (
          <button
            type="button"
            ref={setAnchor("add")}
            onClick={() => setOpenPanel(openPanel === "add" ? null : "add")}
            aria-haspopup="menu"
            aria-expanded={openPanel === "add"}
            className={`${chipBase} gap-1 border-dashed border-border px-3 text-text-muted hover:border-primary hover:text-text md:px-2.5`}
          >
            <Plus className="h-3.5 w-3.5 md:h-3 md:w-3" aria-hidden="true" />
            {t("filters.add")}
          </button>
        )}

        {hasAnyFilter && (
          <button
            type="button"
            onClick={onClearAll}
            className="relative h-9 px-1 text-sm font-medium text-primary before:absolute before:inset-x-0 before:-inset-y-1 before:content-[''] hover:underline md:h-auto md:text-xs md:before:hidden"
          >
            {t("filters.clearAll")}
          </button>
        )}
      </div>

      {isDesktop ? (
        <>
          <FloatingPanel open={openPanel === "add"} anchorRef={anchorFor("add")} onClose={closePanel}>
            {addMenu}
          </FloatingPanel>
          {selectFilters.map((filter) => (
            <FloatingPanel
              key={filter.key}
              open={openPanel === filter.key}
              anchorRef={anchorFor(filter.values.length > 0 ? filter.key : "add")}
              onClose={closePanel}
            >
              {picker(filter, false)}
            </FloatingPanel>
          ))}
        </>
      ) : (
        <BottomSheet
          open={openPanel === "add" || openFilter !== null}
          onClose={closePanel}
          title={openPanel === "add" ? t("filters.addTitle") : (openFilter?.label ?? "")}
        >
          {openPanel === "add" ? addMenu : openFilter ? picker(openFilter, true) : null}
        </BottomSheet>
      )}

      {summary && (
        <div className="text-xs text-text-muted" aria-live="polite">
          {summary}
        </div>
      )}
    </div>
  );
}

interface FilterPickerProps {
  filter: SelectFilter;
  mobile: boolean;
  /** Valori da applicare e chiudere: Applica su mobile, scelta di un valore singolo ovunque. */
  onApply: (values: string[]) => void;
  /** Desktop: ogni scelta si applica subito. */
  onChangeLive: (values: string[]) => void;
  onDone: () => void;
}

function RemoteSource({
  filter,
  query,
  children,
}: {
  filter: SelectFilter;
  query: string;
  children: (remote: RemoteOptions) => ReactNode;
}) {
  const remote = filter.useRemoteOptions!(query);
  return <>{children(remote)}</>;
}

function FilterPicker(props: FilterPickerProps) {
  const [query, setQuery] = useState("");
  const { filter } = props;
  if (filter.remote && filter.useRemoteOptions) {
    return (
      <RemoteSource filter={filter} query={query}>
        {(remote) => {
          // I valori gia' scelti ma fuori dai risultati correnti restano visibili.
          const options = [...remote.options];
          for (const value of filter.values) {
            if (!options.some((o) => o.value === value)) options.unshift({ value, label: value });
          }
          return (
            <PickerBody
              {...props}
              options={options}
              query={query}
              onQueryChange={setQuery}
              showSearch
              heading={query.trim() ? undefined : remote.heading}
              remoteTotal={remote.total}
              isLoading={remote.isLoading}
            />
          );
        }}
      </RemoteSource>
    );
  }
  const needle = query.trim().toLowerCase();
  const options = needle ? filter.options.filter((o) => o.label.toLowerCase().includes(needle)) : filter.options;
  return (
    <PickerBody
      {...props}
      options={options}
      query={query}
      onQueryChange={setQuery}
      // Con pochi valori la ricerca e' rumore: compare solo per le liste lunghe.
      showSearch={filter.options.length > 6}
    />
  );
}

function PickerBody({
  filter,
  mobile,
  onApply,
  onChangeLive,
  onDone,
  options,
  query,
  onQueryChange,
  showSearch,
  heading,
  remoteTotal,
  isLoading,
}: FilterPickerProps & {
  options: FilterOption[];
  query: string;
  onQueryChange: (value: string) => void;
  showSearch: boolean;
  heading?: string;
  remoteTotal?: number;
  isLoading?: boolean;
}) {
  const { t } = useTranslation("common");
  // Mobile: bozza locale applicata all'Applica. Desktop: valori reali, applicazione immediata.
  const [draft, setDraft] = useState(filter.values);
  const values = mobile ? draft : filter.values;
  const setValues = (next: string[]) => (mobile ? setDraft(next) : onChangeLive(next));

  const toggle = (value: string) => {
    if (filter.single) {
      onApply([value]);
      return;
    }
    setValues(values.includes(value) ? values.filter((v) => v !== value) : [...values, value]);
  };
  const searchLabel = t("filters.pickerSearch", { name: filter.label.toLowerCase() });
  const hint =
    remoteTotal !== undefined && remoteTotal > options.length
      ? t("filters.remoteHint", { shown: options.length, total: remoteTotal })
      : undefined;

  return (
    <div className="flex flex-col md:w-72">
      {showSearch && (
        <div className="border-b border-border py-2 md:p-2">
          <input
            // Su smartphone niente focus automatico: aprirebbe subito la tastiera
            // coprendo mezzo elenco.
            autoFocus={!mobile}
            type="search"
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder={searchLabel}
            aria-label={searchLabel}
            className="h-11 w-full rounded-md border border-border bg-surface px-2 text-sm text-text placeholder:text-text-muted md:h-9"
          />
        </div>
      )}
      <ul
        role="listbox"
        aria-label={filter.label}
        aria-multiselectable={filter.single ? undefined : "true"}
        className="max-h-[50dvh] overflow-y-auto py-1 md:max-h-64 md:p-1"
      >
        {heading && <li className="px-3 pb-1 pt-2 text-xs text-text-muted">{heading}</li>}
        {!isLoading && options.length === 0 && (
          <li className="px-3 py-2 text-sm text-text-muted">{t("filters.pickerEmpty")}</li>
        )}
        {options.map((option) => {
          const selected = values.includes(option.value);
          return (
            <li key={option.value} role="option" aria-selected={selected}>
              <button
                type="button"
                onClick={() => toggle(option.value)}
                className="flex h-11 w-full items-center gap-3 rounded-md px-3 text-left text-sm text-text hover:bg-surface-hover md:h-auto md:gap-2 md:py-1.5"
              >
                <span
                  aria-hidden="true"
                  className={`flex h-5 w-5 shrink-0 items-center justify-center border md:h-4 md:w-4 ${
                    filter.single ? "rounded-full" : "rounded"
                  } ${selected ? "border-primary bg-primary text-primary-contrast" : "border-border"}`}
                >
                  {selected && <Check className="h-3.5 w-3.5 md:h-3 md:w-3" />}
                </span>
                <span className="flex-1 truncate">{option.label}</span>
                {option.count !== undefined && <span className="text-xs text-text-muted">{option.count}</span>}
              </button>
            </li>
          );
        })}
        {hint && <li className="px-3 py-2 text-xs text-text-muted">{hint}</li>}
      </ul>
      {mobile ? (
        <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
          {filter.single ? (
            <span />
          ) : (
            <Button variant="ghost" onClick={() => setDraft([])} disabled={draft.length === 0}>
              {t("filters.reset")}
            </Button>
          )}
          {!filter.single && (
            <Button onClick={() => onApply(draft)}>
              {t("filters.apply")}
              {draft.length > 0 ? ` · ${draft.length}` : ""}
            </Button>
          )}
        </div>
      ) : (
        !filter.single && (
          <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-text-muted">
            <span>{t("filters.selectedCount", { count: values.length })}</span>
            <span className="flex items-center gap-3">
              {values.length > 0 && (
                <button type="button" onClick={() => onChangeLive([])} className="text-primary hover:underline">
                  {t("filters.deselect")}
                </button>
              )}
              <button type="button" onClick={onDone} className="font-medium text-primary hover:underline">
                {t("filters.done")}
              </button>
            </span>
          </div>
        )
      )}
    </div>
  );
}
