import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";

import type { ComboboxOption } from "../../components/ui/Combobox";
import type { Category, CategoryKind } from "../../types/api";

export interface CategoryOption {
  id: string;
  label: string;
}

/** Etichetta del kind: namespace "enums" (SPEC_FE_REDESIGN §27), stesso
 * pattern di `ruleFieldLabel`/`aiProviderLabel`. */
export function categoryKindLabel(t: TFunction, kind: CategoryKind): string {
  return t(`enums:categoryKind.${kind}`);
}

/** Nome da mostrare per una categoria (PLAN_TAXONOMY_I18N.md): le categorie
 * di sistema (`is_system=true`) hanno un `code` stabile tradotto nel
 * namespace "categories" (`app/classification/taxonomy.py` e' l'unica fonte
 * di verita', da cui sono generate le 149 chiavi in
 * `locales/{it,en}/categories.json`); le categorie utente (testo libero,
 * MAI tradotto) mostrano sempre `name` cosi' com'e'. `keySeparator: false`
 * e' necessario perche' molti `code` contengono un punto (es.
 * "casa.affitto") che altrimenti i18next interpreterebbe come nesting,
 * collidendo con la chiave radice "casa" (che e' una stringa foglia, non un
 * oggetto). */
export function categoryDisplayName(t: TFunction, category: Category): string {
  return category.is_system ? t(category.code, { ns: "categories", keySeparator: false }) : category.name;
}

/** Etichetta gerarchica ("Alimentari › Supermercato") invece di un vero
 * albero navigabile — sufficiente per selezionare una categoria in un form
 * (correzione transazione, creazione regola). Il tree management completo
 * (SPEC_FE §46) vive nella pagina dedicata `/settings/categories`. */
export function buildCategoryOptions(categories: Category[] | undefined, t: TFunction): CategoryOption[] {
  if (!categories) return [];
  const byId = new Map(categories.map((c) => [c.id, c]));
  const options = categories
    .filter((c) => c.is_active)
    .map((c) => {
      const parent = c.parent_id ? byId.get(c.parent_id) : undefined;
      return {
        id: c.id,
        label: parent
          ? `${categoryDisplayName(t, parent)} › ${categoryDisplayName(t, c)}`
          : categoryDisplayName(t, c),
        // Numerico, non una stringa concatenata: con `localeCompare` "100-99"
        // ordinava PRIMA di "100-101" (confronto lessicografico carattere per
        // carattere, "1" < "9"), mescolando l'ordine dei figli non appena la
        // tassonomia ha superato le due cifre di sort_order (23 padri x fino
        // a ~10 figli ciascuno). Un padre puo' avere al massimo migliaia di
        // figli prima che questa combinazione collida con quella del padre
        // successivo — ampiamente sufficiente per una tassonomia curata.
        sortKey: (parent?.sort_order ?? c.sort_order) * 10_000 + c.sort_order,
      };
    });
  options.sort((a, b) => a.sortKey - b.sortKey);
  return options.map(({ id, label }) => ({ id, label }));
}

// Cache per riferimento dell'array `categories` (stabile tra i render finche'
// React Query non lo rifetcha davvero) E per lingua corrente (un cambio
// lingua non cambia l'array `categories`, ma cambia il risultato di
// `categoryDisplayName` per le categorie di sistema — la cache deve
// invalidarsi anche su quello, non solo sul riferimento dell'array):
// `categoryLabel` e' spesso invocata dentro un `.map()` sulle righe di una
// lista (transazioni, regole) — senza questa cache ogni singola riga
// ricostruiva e riordinava l'intero elenco di opzioni solo per leggerne una
// label, un lavoro O(n log n) ripetuto n volte per un totale O(n² log n)
// sulla pagina. La label non ha comunque bisogno dell'ordinamento di
// `buildCategoryOptions`, solo di un lookup.
const _labelCacheByCategories = new WeakMap<Category[], Map<string, Map<string, string>>>();

function labelsById(categories: Category[], t: TFunction, language: string): Map<string, string> {
  let byLanguage = _labelCacheByCategories.get(categories);
  if (!byLanguage) {
    byLanguage = new Map();
    _labelCacheByCategories.set(categories, byLanguage);
  }
  const cached = byLanguage.get(language);
  if (cached) return cached;

  const byId = new Map(categories.map((c) => [c.id, c]));
  const labels = new Map<string, string>();
  for (const c of categories) {
    const parent = c.parent_id ? byId.get(c.parent_id) : undefined;
    labels.set(
      c.id,
      parent ? `${categoryDisplayName(t, parent)} › ${categoryDisplayName(t, c)}` : categoryDisplayName(t, c),
    );
  }
  byLanguage.set(language, labels);
  return labels;
}

function categoryLabel(
  categories: Category[] | undefined,
  categoryId: string | null,
  uncategorized: string,
  t: TFunction,
  language: string,
): string {
  if (!categoryId || !categories) return uncategorized;
  return labelsById(categories, t, language).get(categoryId) ?? uncategorized;
}

/** Hook che lega `categoryLabel` alla lingua corrente — il fallback
 * "Non categorizzato" vive in i18next (namespace "categories"), non piu'
 * come stringa italiana hardcoded nella funzione pura. */
export function useCategoryLabel(): (categories: Category[] | undefined, categoryId: string | null) => string {
  const { t, i18n } = useTranslation("categories");
  const uncategorized = t("uncategorized");
  return (categories, categoryId) => categoryLabel(categories, categoryId, uncategorized, t, i18n.language);
}

/** Opzioni per `Combobox` (rework tassonomia, da ~14 a ~150 categorie: un
 * `<select>` piatto non e' piu' usabile) — raggruppate per padre cosi' il
 * popover si sfoglia per blocco invece che come un'unica lista lunghissima;
 * la ricerca del Combobox resta comunque il modo principale per trovarne
 * una specifica. Le radici senza figli (es. "Donazioni") restano
 * selezionabili, non raggruppate. */
export function buildCategoryComboboxOptions(categories: Category[] | undefined, t: TFunction): ComboboxOption[] {
  if (!categories) return [];
  const byId = new Map(categories.map((c) => [c.id, c]));
  const options = categories
    .filter((c) => c.is_active)
    .map((c) => {
      const parent = c.parent_id ? byId.get(c.parent_id) : undefined;
      return {
        value: c.id,
        label: categoryDisplayName(t, c),
        group: parent ? categoryDisplayName(t, parent) : undefined,
        sortKey: (parent?.sort_order ?? c.sort_order) * 10_000 + c.sort_order,
      };
    });
  options.sort((a, b) => a.sortKey - b.sortKey);
  return options.map(({ value, label, group }) => ({ value, label, group }));
}
