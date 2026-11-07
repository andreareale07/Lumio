import { useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, Check, ChevronLeft, ChevronRight, Tag } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { PeriodNavigator } from "../../components/filters/PeriodNavigator";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { SwipeableRow } from "../../components/ui/SwipeableRow";
import { hapticSuccess } from "../../lib/haptics";
import { useAccounts } from "../accounts/api";
import { useCategories } from "../categories/api";
import { buildCategoryOptions, useCategoryLabel } from "../categories/utils";
import { formatDate, formatSignedMoney } from "../../lib/format";
import { usePeriodNavigator } from "../../lib/usePeriodNavigator";
import { TRANSACTION_TYPES, type Transaction } from "../../types/api";
import {
  useConfirmTransaction,
  useTransactionListSummary,
  useTransactionReviewSummary,
  useTransactions,
} from "./api";
import { useTransactionTypeLabel } from "./labels";
import { TransactionDetailDrawer } from "./TransactionDetailDrawer";
import { TransactionFilterBar, type SelectFilter, type StaticFilterChip } from "./TransactionFilterBar";

const PAGE_SIZE = 25;

export function TransactionsPage() {
  const { t } = useTranslation("transactions");
  const transactionTypeLabel = useTransactionTypeLabel();
  const categoryLabel = useCategoryLabel();
  const [searchParams, setSearchParams] = useSearchParams();
  const [offset, setOffset] = useState(0);
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);
  const confirmTransaction = useConfirmTransaction();

  // Filtri multipli: parametri ripetuti nell'URL (`?category=a&category=b`).
  const accountIds = searchParams.getAll("account");
  const categoryIds = searchParams.getAll("category");
  const transactionTypes = searchParams.getAll("type");
  const merchants = searchParams.getAll("merchant");
  const importId = searchParams.get("import") ?? "";
  const noMerchant = searchParams.get("no_merchant") === "1";
  const reviewOnly = searchParams.get("review") === "1";
  const urlQuery = searchParams.get("q") ?? "";
  const { currentPeriod } = usePeriodNavigator({
    granularities: ["day", "week", "month", "quarter", "semester", "year"],
    allowAll: true,
  });

  const { data: accounts } = useAccounts();
  const { data: categories } = useCategories();
  const categoryOptions = buildCategoryOptions(categories, t);
  const accountsById = useMemo(() => new Map((accounts ?? []).map((a) => [a.id, a])), [accounts]);

  // "Da verificare"/un import specifico sono viste mirate: l'utente vuole
  // vedere TUTTE le righe che rispondono a quel criterio, non solo quelle
  // che ricadono ANCHE nel periodo attualmente selezionato (bug reale: il
  // badge conta le righe da verificare senza vincolo di periodo — vedi
  // sotto — ma la lista applicava comunque il periodo corrente, risultando
  // vuota ogni volta che le righe segnalate erano di un mese diverso).
  const bypassPeriodFilter = reviewOnly || !!importId;
  const baseFilters = {
    financial_account_id: accountIds,
    category_id: categoryIds,
    q: urlQuery || undefined,
    merchant: merchants,
    no_merchant: noMerchant ? true : undefined,
    transaction_type: transactionTypes,
    date_from: bypassPeriodFilter ? undefined : currentPeriod.date_from,
    date_to: bypassPeriodFilter ? undefined : currentPeriod.date_to,
    import_id: importId || undefined,
    needs_review: reviewOnly ? true : undefined,
  };
  const filters = { ...baseFilters, limit: PAGE_SIZE, offset };
  const { data: transactions, isLoading, isError, refetch } = useTransactions(filters);
  const { data: listSummary } = useTransactionListSummary(baseFilters);
  // Il conteggio "da verificare" resta scoped allo stesso import/conto del
  // filtro attivo (se presenti), ma NON al periodo/tipo/categoria — deve
  // restare stabile mentre l'utente affina gli altri filtri, altrimenti il
  // numero sul badge cambierebbe ad ogni click perdendo di significato come
  // "quante ne restano da guardare in totale".
  const { data: reviewSummary } = useTransactionReviewSummary({
    financial_account_id: accountIds.length === 1 ? accountIds[0] : undefined,
    import_id: importId || undefined,
  });

  // Un cambio di periodo e' pilotato dai controlli interni di
  // PeriodNavigator, non da `updateFilter` sotto — senza questo reset un
  // utente a pagina 2 di "maggio" che passa a "giugno" resterebbe su un
  // offset sbagliato (nessuna riga, o righe del mese sbagliato).
  useEffect(() => {
    setOffset(0);
  }, [currentPeriod.date_from, currentPeriod.date_to]);

  const setFilterValues = (key: string, values: string[]) => {
    setOffset(0);
    const next = new URLSearchParams(searchParams);
    next.delete(key);
    values.forEach((value) => next.append(key, value));
    setSearchParams(next);
  };

  const updateFilter = (key: string, value: string) => {
    setOffset(0);
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  };

  // Ricerca testuale: lo stato locale segue la digitazione, l'URL (e quindi la
  // query) si aggiorna dopo una breve pausa. Il valore nell'URL e' la fonte di
  // verita': un "Azzera filtri" o un link esterno lo riallineano.
  const [searchText, setSearchText] = useState(urlQuery);
  useEffect(() => {
    setSearchText(urlQuery);
  }, [urlQuery]);
  useEffect(() => {
    const trimmed = searchText.trim();
    if (trimmed === urlQuery) return;
    const timer = setTimeout(() => {
      setOffset(0);
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (trimmed) next.set("q", trimmed);
          else next.delete("q");
          return next;
        },
        { replace: true },
      );
    }, 300);
    return () => clearTimeout(timer);
  }, [searchText, urlQuery, setSearchParams]);

  const removeFilters = (...keys: string[]) => {
    setOffset(0);
    const next = new URLSearchParams(searchParams);
    keys.forEach((key) => next.delete(key));
    setSearchParams(next);
  };
  const PERIOD_KEYS = ["mode", "granularity", "anchor", "from", "to"];
  const hasPeriodOverride = PERIOD_KEYS.some((key) => searchParams.has(key));
  const hasFilters = !!(
    accountIds.length ||
    categoryIds.length ||
    transactionTypes.length ||
    merchants.length ||
    importId ||
    noMerchant ||
    reviewOnly ||
    urlQuery
  );
  // "Azzera tutto" riporta anche il periodo al default: altrimenti un link che
  // arriva con un periodo fisso (es. dal drill-down) lascia zero risultati
  // senza che l'utente capisca perche'.
  const hasAnyFilter = hasFilters || hasPeriodOverride;
  const clearAllFilters = () =>
    removeFilters("account", "category", "type", "import", "merchant", "no_merchant", "review", "q", ...PERIOD_KEYS);

  const selectFilters: SelectFilter[] = [
    {
      key: "account",
      label: t("page.filters.account"),
      values: accountIds,
      options: (accounts ?? []).map((account) => ({ value: account.id, label: account.name })),
    },
    {
      key: "category",
      label: t("page.filters.category"),
      values: categoryIds,
      options: categoryOptions.map((option) => ({ value: option.id, label: option.label })),
    },
    {
      key: "type",
      label: t("page.filters.type"),
      values: transactionTypes,
      options: TRANSACTION_TYPES.map((type) => ({ value: type, label: transactionTypeLabel(type) })),
    },
    { key: "merchant", label: t("page.filters.merchant"), values: merchants, options: [], remote: true },
  ];

  const staticChips: StaticFilterChip[] = [];
  if (noMerchant) {
    staticChips.push({
      key: "no_merchant",
      label: t("page.filters.noMerchant"),
      onRemove: () => removeFilters("no_merchant"),
    });
  }
  if (importId) {
    staticChips.push({ key: "import", label: t("page.filters.importChip"), onRemove: () => removeFilters("import") });
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-lg font-semibold text-text">{t("page.title")}</h1>
      </div>

      <PeriodNavigator granularities={["day", "week", "month", "quarter", "semester", "year"]} allowAll />

      <TransactionFilterBar
        searchText={searchText}
        onSearchTextChange={setSearchText}
        selectFilters={selectFilters}
        onSetFilterValues={setFilterValues}
        staticChips={staticChips}
        review={
          reviewSummary?.needs_review
            ? { count: reviewSummary.needs_review, active: reviewOnly, onToggle: () => updateFilter("review", reviewOnly ? "" : "1") }
            : null
        }
        hasAnyFilter={hasAnyFilter}
        onClearAll={clearAllFilters}
        summary={listSummary}
      />

      {isLoading && <SkeletonRows rows={6} />}
      {isError && (
        <ErrorState message={t("page.loadError")} onRetry={() => void refetch()} />
      )}

      {!isLoading && !isError && transactions && transactions.length === 0 && (
        <EmptyState
          icon={ArrowLeftRight}
          title={hasAnyFilter ? t("page.noResults.title") : t("page.empty.title")}
          description={hasAnyFilter ? t("page.noResults.description") : t("page.empty.description")}
          action={
            hasAnyFilter ? (
              <Button variant="secondary" size="sm" onClick={clearAllFilters}>
                {t("page.filters.clearAll")}
              </Button>
            ) : undefined
          }
        />
      )}

      {!isLoading && !isError && transactions && transactions.length > 0 && (
        <>
          {/* Desktop: tabella (SPEC_FE §23) */}
          <div className="hidden overflow-hidden rounded-xl border border-border md:block">
            <table className="w-full text-sm">
              <thead className="bg-surface-hover text-left text-text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">{t("page.table.date")}</th>
                  <th className="px-3 py-2 font-medium">{t("page.table.description")}</th>
                  <th className="px-3 py-2 font-medium">{t("page.table.account")}</th>
                  <th className="px-3 py-2 font-medium">{t("page.table.category")}</th>
                  <th className="px-3 py-2 font-medium">{t("page.table.type")}</th>
                  <th className="px-3 py-2 text-right font-medium">{t("page.table.amount")}</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((transaction) => (
                  <tr
                    key={transaction.id}
                    onClick={() => setSelectedTransaction(transaction)}
                    className="cursor-pointer border-t border-border bg-surface hover:bg-surface-hover"
                  >
                    <td className="px-3 py-2 text-text-muted">{formatDate(transaction.transaction_date)}</td>
                    <td className="px-3 py-2 text-text">{transaction.merchant ?? transaction.description_raw}</td>
                    <td className="px-3 py-2 text-text-muted">
                      {accountsById.get(transaction.financial_account_id)?.name ?? t("page.table.noAccount")}
                    </td>
                    <td className="px-3 py-2 text-text-muted">
                      <span className="inline-flex items-center gap-1.5">
                        {categoryLabel(categories, transaction.category_id)}
                        {transaction.needs_review && <Badge tone="warning">{t("page.table.needsReviewBadge")}</Badge>}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-text-muted">{transactionTypeLabel(transaction.transaction_type)}</td>
                    <td className="font-numeric px-3 py-2 text-right text-text">
                      {formatSignedMoney(transaction.amount, transaction.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile: card list (SPEC_FE §24) */}
          <div className="flex flex-col gap-2 md:hidden">
            {transactions.map((transaction) => (
              <SwipeableRow
                key={transaction.id}
                // Scorciatoie: la conferma ha senso solo se c'e' una categoria da
                // confermare; "Categoria" apre lo stesso dettaglio del tocco.
                startAction={
                  transaction.needs_review && transaction.category_id
                    ? {
                        label: t("page.swipe.confirm"),
                        icon: Check,
                        className: "bg-success",
                        onTrigger: () =>
                          confirmTransaction.mutate(transaction.id, { onSuccess: () => hapticSuccess() }),
                      }
                    : undefined
                }
                endAction={{
                  label: t("page.swipe.categorize"),
                  icon: Tag,
                  className: "bg-primary",
                  onTrigger: () => setSelectedTransaction(transaction),
                }}
              >
              <button
                onClick={() => setSelectedTransaction(transaction)}
                className="flex w-full flex-col gap-1 rounded-xl border border-border bg-surface p-3 text-left"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-text">{transaction.merchant ?? transaction.description_raw}</span>
                  <span className="font-numeric text-text">
                    {formatSignedMoney(transaction.amount, transaction.currency)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm text-text-muted">
                  <span className="inline-flex items-center gap-1.5">
                    {categoryLabel(categories, transaction.category_id)}
                    {transaction.needs_review && <Badge tone="warning">{t("page.table.needsReviewBadge")}</Badge>}
                  </span>
                  <span>{formatDate(transaction.transaction_date)}</span>
                </div>
              </button>
              </SwipeableRow>
            ))}
          </div>

          <div className="flex items-center justify-between">
            <Button
              variant="link"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              <ChevronLeft className="h-4 w-4" /> {t("page.pagination.previous")}
            </Button>
            <Button
              variant="link"
              size="sm"
              disabled={transactions.length < PAGE_SIZE}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              {t("page.pagination.next")} <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </>
      )}

      <TransactionDetailDrawer transaction={selectedTransaction} onClose={() => setSelectedTransaction(null)} />
    </div>
  );
}
