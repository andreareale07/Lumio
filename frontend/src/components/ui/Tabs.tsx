interface Tab {
  key: string;
  label: string;
}

interface TabsProps {
  tabs: Tab[];
  active: string;
  onChange: (key: string) => void;
}

/** Tab semplice (SPEC_FE §21 Account Detail: Overview | Movimenti |
 * Analytics), navigazione da tastiera nativa via `role="tab"`.
 *
 * `overflow-x-auto` + `flex-nowrap`: con poche tab (3-4) il contenitore non
 * arriva mai a riempire la larghezza, ma una pagina con piu' sezioni (es.
 * Investimenti, 6 tab) su viewport mobile altrimenti farebbe scorrere
 * l'INTERA pagina in orizzontale, o taglierebbe le ultime tab fuori
 * schermo senza alcun modo di raggiungerle (bug osservato: "Performance"/
 * "Conti" irraggiungibili a 375px prima di questo fix) — deve scorrere
 * solo la barra delle tab, mai il body (SPEC_FE responsive). */
export function Tabs({ tabs, active, onChange }: TabsProps) {
  return (
    <div
      role="tablist"
      aria-label="Sezioni"
      className="flex flex-nowrap gap-1 overflow-x-auto border-b border-border"
    >
      {tabs.map((tab) => (
        <button
          key={tab.key}
          role="tab"
          type="button"
          aria-selected={tab.key === active}
          onClick={() => onChange(tab.key)}
          className={`-mb-px shrink-0 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
            tab.key === active
              ? "border-primary text-primary"
              : "border-transparent text-text-muted hover:text-text"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
