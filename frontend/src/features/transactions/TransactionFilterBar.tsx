import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";

import {
  FilterBar,
  type FilterOption,
  type RemoteOptions,
  type SelectFilter,
  type StaticFilterChip,
} from "../../components/filters/FilterBar";
import { formatMoney } from "../../lib/format";
import type { TransactionListSummary } from "../../types/api";
import { useTransactionMerchants } from "./api";

export type { FilterOption, SelectFilter, StaticFilterChip };

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

/** Merchant: elenco remoto con ricerca (`GET /transactions/merchants?q=`), i
 * piu' frequenti con conteggi e "N su totale". */
function useMerchantOptions(query: string): RemoteOptions {
  const { t } = useTranslation("transactions");
  const merchants = useTransactionMerchants(query);
  return {
    options: (merchants.data?.items ?? []).map((m) => ({ value: m.merchant, label: m.merchant, count: m.count })),
    total: merchants.data?.total ?? 0,
    isLoading: merchants.isLoading,
    heading: t("page.filters.mostFrequent"),
  };
}

/** Barra filtri di Movimenti: la `FilterBar` condivisa con la ricerca, il filtro
 * rapido "Da verificare", i merchant remoti e il riepilogo conteggio/saldo. Il
 * periodo resta nel suo selettore ma "Azzera filtri" lo riporta al default. */
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

  return (
    <FilterBar
      search={{
        id: "transactions-search",
        label: t("page.search.label"),
        placeholder: t("page.search.placeholder"),
        value: searchText,
        onChange: onSearchTextChange,
      }}
      selectFilters={selectFilters.map((filter) =>
        filter.remote ? { ...filter, useRemoteOptions: useMerchantOptions } : filter,
      )}
      onSetFilterValues={onSetFilterValues}
      staticChips={staticChips}
      quickFilters={
        review
          ? [
              {
                key: "review",
                label: t("page.needsReview", { count: review.count }),
                icon: <TriangleAlert className="h-3 w-3" aria-hidden="true" />,
                active: review.active,
                onToggle: review.onToggle,
              },
            ]
          : []
      }
      hasAnyFilter={hasAnyFilter}
      onClearAll={onClearAll}
      summary={
        summary ? (
          <>
            {t("page.summary.count", { count: summary.count })}
            {(Number(summary.income) > 0 || Number(summary.expenses) > 0) && (
              <>
                {" · "}
                {t("page.summary.income", { value: formatMoney(summary.income, summary.currency) })}
                {" · "}
                {t("page.summary.expenses", { value: formatMoney(summary.expenses, summary.currency) })}
              </>
            )}
          </>
        ) : undefined
      }
    />
  );
}
