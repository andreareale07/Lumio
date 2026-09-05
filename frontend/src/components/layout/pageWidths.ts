/** Larghezza di default per pagine-form/riepilogo (centrate, contenuto
 * limitato): usare `mx-auto flex max-w-4xl flex-col gap-4` (o max-w-5xl/6xl
 * a seconda della densità) come già fanno la maggior parte delle pagine.
 * Per pagine dati-intensive (tabelle larghe, liste con molte colonne/filtri
 * che cresceranno nel tempo) usare invece PAGE_WIDTH_WIDE: nessun
 * centraggio, usa tutta la larghezza disponibile nel layout `<main>`
 * (AppShell.tsx) invece di restare incollata al centro dello schermo. */
export const PAGE_WIDTH_WIDE = "flex w-full flex-col gap-4";
