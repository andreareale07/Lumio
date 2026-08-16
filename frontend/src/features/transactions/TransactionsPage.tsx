import { useEffect, useMemo, useState } from "react";
import { ArrowLeftRight, ChevronLeft, ChevronRight } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { PeriodNavigator } from "../../components/filters/PeriodNavigator";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Select } from "../../components/ui/Select";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { useAccounts } from "../accounts/api";
import { useCategories } from "../categories/api";
import { buildCategoryOptions, categoryLabel } from "../categories/utils";
import { formatDate, formatSignedMoney } from "../../lib/format";
import { usePeriodNavigator } from "../../lib/usePeriodNavigator";
import { TRANSACTION_TYPES, type Transaction } from "../../types/api";
import { useTransactionReviewSummary, useTransactions } from "./api";
import { TRANSACTION_TYPE_LABELS } from "./labels";
import { TransactionDetailDrawer } from "./TransactionDetailDrawer";

const PAGE_SIZE = 25;

export function TransactionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [offset, setOffset] = useState(0);
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);

  const accountId = searchParams.get("account") ?? "";
  const categoryId = searchParams.get("category") ?? "";
  const transactionType = searchParams.get("type") ?? "";
  const importId = searchParams.get("import") ?? "";
  const reviewOnly = searchParams.get("review") === "1";
  const { currentPeriod } = usePeriodNavigator({
    granularities: ["day", "week", "month", "quarter", "semester", "year"],
    allowAll: true,
  });

  const { data: accounts } = useAccounts();
  const { data: categories } = useCategories();
  const categoryOptions = buildCategoryOptions(categories);
  const accountsById = useMemo(() => new Map((accounts ?? []).map((a) => [a.id, a])), [accounts]);

  // "Da verificare"/un import specifico sono viste mirate: l'utente vuole
  // vedere TUTTE le righe che rispondono a quel criterio, non solo quelle
  // che ricadono ANCHE nel periodo attualmente selezionato (bug reale: il
  // badge conta le righe da verificare senza vincolo di periodo — vedi
  // sotto — ma la lista applicava comunque il periodo corrente, risultando
  // vuota ogni volta che le righe segnalate erano di un mese diverso).
  const bypassPeriodFilter = reviewOnly || !!importId;
  const filters = {
    financial_account_id: accountId || undefined,
    category_id: categoryId || undefined,
    transaction_type: transactionType || undefined,
    date_from: bypassPeriodFilter ? undefined : currentPeriod.date_from,
    date_to: bypassPeriodFilter ? undefined : currentPeriod.date_to,
    import_id: importId || undefined,
    needs_review: reviewOnly ? true : undefined,
    limit: PAGE_SIZE,
    offset,
  };
  const { data: transactions, isLoading, isError, refetch } = useTransactions(filters);
  // Il conteggio "da verificare" resta scoped allo stesso import/conto del
  // filtro attivo (se presenti), ma NON al periodo/tipo/categoria — deve
  // restare stabile mentre l'utente affina gli altri filtri, altrimenti il
  // numero sul badge cambierebbe ad ogni click perdendo di significato come
  // "quante ne restano da guardare in totale".
  const { data: reviewSummary } = useTransactionReviewSummary({
    financial_account_id: accountId || undefined,
    import_id: importId || undefined,
  });

  // Un cambio di periodo e' pilotato dai controlli interni di
  // PeriodNavigator, non da `updateFilter` sotto — senza questo reset un
  // utente a pagina 2 di "maggio" che passa a "giugno" resterebbe su un
  // offset sbagliato (nessuna riga, o righe del mese sbagliato).
  useEffect(() => {
    setOffset(0);
  }, [currentPeriod.date_from, currentPeriod.date_to]);

  const updateFilter = (key: string, value: string) => {
    setOffset(0);
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  };

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-lg font-semibold text-text">Movimenti</h1>
        <PeriodNavigator granularities={["day", "week", "month", "quarter", "semester", "year"]} allowAll />
      </div>

      <div className="flex flex-wrap gap-3">
        <Select
          aria-label="Conto"
          value={accountId}
          onChange={(e) => updateFilter("account", e.target.value)}
          className="w-auto"
        >
          <option value="">Tutti i conti</option>
          {(accounts ?? []).map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Categoria"
          value={categoryId}
          onChange={(e) => updateFilter("category", e.target.value)}
          className="w-auto"
        >
          <option value="">Tutte le categorie</option>
          {categoryOptions.map((option) => (
            <option key={option.id} value={option.id}>
              {option.label}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Tipo"
          value={transactionType}
          onChange={(e) => updateFilter("type", e.target.value)}
          className="w-auto"
        >
          <option value="">Tutti i tipi</option>
          {TRANSACTION_TYPES.map((type) => (
            <option key={type} value={type}>
              {TRANSACTION_TYPE_LABELS[type]}
            </option>
          ))}
        </Select>
        {!!reviewSummary?.needs_review && (
          <button
            type="button"
            onClick={() => updateFilter("review", reviewOnly ? "" : "1")}
            aria-pressed={reviewOnly}
            className={`inline-flex ${reviewOnly ? "" : "opacity-80 hover:opacity-100"}`}
          >
            <Badge tone={reviewOnly ? "warning" : "neutral"}>
              ⚠ {reviewSummary.needs_review} da verificare
            </Badge>
          </button>
        )}
      </div>

      {isLoading && <SkeletonRows rows={6} />}
      {isError && (
        <ErrorState message="Non siamo riusciti a caricare i tuoi movimenti." onRetry={() => void refetch()} />
      )}

      {!isLoading && !isError && transactions && transactions.length === 0 && (
        <EmptyState
          icon={ArrowLeftRight}
          title="Nessun movimento"
          description="I movimenti importati o creati manualmente appariranno qui."
        />
      )}

      {!isLoading && !isError && transactions && transactions.length > 0 && (
        <>
          {/* Desktop: tabella (SPEC_FE §23) */}
          <div className="hidden overflow-hidden rounded-xl border border-border md:block">
            <table className="w-full text-sm">
              <thead className="bg-surface-hover text-left text-text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Data</th>
                  <th className="px-3 py-2 font-medium">Descrizione</th>
                  <th className="px-3 py-2 font-medium">Conto</th>
                  <th className="px-3 py-2 font-medium">Categoria</th>
                  <th className="px-3 py-2 font-medium">Tipo</th>
                  <th className="px-3 py-2 text-right font-medium">Importo</th>
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
                      {accountsById.get(transaction.financial_account_id)?.name ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-text-muted">
                      <span className="inline-flex items-center gap-1.5">
                        {categoryLabel(categories, transaction.category_id)}
                        {transaction.needs_review && <Badge tone="warning">da verificare</Badge>}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-text-muted">{TRANSACTION_TYPE_LABELS[transaction.transaction_type]}</td>
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
              <button
                key={transaction.id}
                onClick={() => setSelectedTransaction(transaction)}
                className="flex flex-col gap-1 rounded-xl border border-border bg-surface p-3 text-left"
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
                    {transaction.needs_review && <Badge tone="warning">da verificare</Badge>}
                  </span>
                  <span>{formatDate(transaction.transaction_date)}</span>
                </div>
              </button>
            ))}
          </div>

          <div className="flex items-center justify-between">
            <Button
              variant="link"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              <ChevronLeft className="h-4 w-4" /> Precedenti
            </Button>
            <Button
              variant="link"
              size="sm"
              disabled={transactions.length < PAGE_SIZE}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Successivi <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </>
      )}

      <TransactionDetailDrawer transaction={selectedTransaction} onClose={() => setSelectedTransaction(null)} />
    </div>
  );
}
