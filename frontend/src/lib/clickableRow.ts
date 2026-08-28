/** Affordance hover condivisa per righe/card cliccabili (FETTA 0 del redesign
 * Spese/Entrate/Dashboard, decisa con l'utente via mockup interattivi prima
 * del codice): uno sfondo "ghost" leggero sull'intera riga al passaggio del
 * mouse/focus, più una freccina che appare e si sposta leggermente in alto a
 * destra — mai un contorno permanente, lo stile piatto e' voluto.
 *
 * Un solo pattern condiviso invece di ripeterlo a mano in ogni componente:
 * usato da `KpiCard` e dalle righe cliccabili della gerarchia
 * categorie/merchant su Spese/Entrate. */
export const clickableRowClasses = "group rounded-lg -m-1 p-1 transition-colors hover:bg-surface-hover";

/** Classi per l'icona freccina che segnala "questo apre qualcos'altro" — da
 * applicare a un'icona lucide-react (tipicamente `ArrowUpRight`) dentro un
 * elemento che porta `clickableRowClasses`. */
export const clickableRowArrowClasses =
  "h-3.5 w-3.5 text-text-muted opacity-0 -translate-y-0.5 translate-x-0.5 transition-all group-hover:translate-x-0 group-hover:translate-y-0 group-hover:opacity-100 group-focus-visible:opacity-100";
