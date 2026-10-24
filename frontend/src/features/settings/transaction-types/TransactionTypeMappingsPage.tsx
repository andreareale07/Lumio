import { useEffect, useMemo, useState } from "react";
import { Search, Tags } from "lucide-react";
import { useTranslation } from "react-i18next";

import { PAGE_WIDTH_WIDE } from "../../../components/layout/pageWidths";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { Pagination } from "../../../components/ui/Pagination";
import { Select } from "../../../components/ui/Select";
import { SkeletonRows } from "../../../components/ui/Skeleton";
import { usePagedList } from "../../../lib/usePagedList";
import { useTransactionTypeLabel } from "../../transactions/labels";
import { TRANSACTION_TYPES, type TransactionType, type TransactionTypeLabel } from "../../../types/api";
import { useDeleteTransactionTypeMapping, useTransactionTypeLabels, useUpsertTransactionTypeMapping, useUsedParserTypes } from "./api";
import { parserTypeLabel } from "./labels";

/** Milestone 09.5: override configurabile dall'utente della mappatura
 * `source_type_raw` -> tipo canonico di un parser (SPEC §17). Senza un
 * override, resta il comportamento predefinito del parser — onesto ma
 * generico (vedi CLAUDE.md, "un parser mappa solo cio' che l'etichetta
 * afferma"). Salvare un override qui applica SUBITO la rimappatura anche
 * alle transazioni gia' importate con quella etichetta, tranne quelle che
 * l'utente ha gia' corretto a mano (mai sovrascritte, vedi backend). */
export function TransactionTypeMappingsPage() {
  const { t } = useTranslation("settings");
  const { data: parserTypes, isLoading, isError, refetch } = useUsedParserTypes();
  const [selectedParser, setSelectedParser] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedParser && parserTypes && parserTypes.length > 0) {
      setSelectedParser(parserTypes[0]);
    }
  }, [parserTypes, selectedParser]);

  return (
    <div className={PAGE_WIDTH_WIDE}>
      <h1 className="text-lg font-semibold text-text">{t("items.transactionTypes.label")}</h1>

      <p className="text-sm text-text-muted">
        {t("items.transactionTypes.pageDescription")}
      </p>

      {isLoading && <SkeletonRows rows={3} />}
      {isError && (
        <ErrorState message={t("items.transactionTypes.page.parsersError")} onRetry={() => void refetch()} />
      )}

      {!isLoading && !isError && parserTypes && parserTypes.length === 0 && (
        <EmptyState
          icon={Tags}
          title={t("items.transactionTypes.page.noParsers.title")}
          description={t("items.transactionTypes.page.noParsers.description")}
        />
      )}

      {!isLoading && !isError && parserTypes && parserTypes.length > 1 && (
        <Select
          label={t("items.transactionTypes.page.parserSelect")}
          value={selectedParser ?? ""}
          onChange={(e) => setSelectedParser(e.target.value)}
        >
          {parserTypes.map((parserType) => (
            <option key={parserType} value={parserType}>
              {parserTypeLabel(parserType)}
            </option>
          ))}
        </Select>
      )}

      {selectedParser && <LabelsList parserType={selectedParser} />}
    </div>
  );
}

function LabelsList({ parserType }: { parserType: string }) {
  const { t } = useTranslation("settings");
  const { data: labels, isLoading, isError, refetch } = useTransactionTypeLabels(parserType);

  if (isLoading) return <SkeletonRows rows={3} />;
  if (isError) {
    return <ErrorState message={t("items.transactionTypes.page.labelsError")} onRetry={() => void refetch()} />;
  }
  if (!labels || labels.length === 0) {
    return (
      <EmptyState
        icon={Tags}
        title={t("items.transactionTypes.page.noLabels.title")}
        description={t("items.transactionTypes.page.noLabels.description")}
      />
    );
  }

  return <LabelsTable parserType={parserType} labels={labels} />;
}

const PAGE_SIZE = 8;
type LabelFilter = "all" | "overrides";

function LabelsTable({ parserType, labels }: { parserType: string; labels: TransactionTypeLabel[] }) {
  const { t } = useTranslation("settings");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<LabelFilter>("all");

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return labels
      .filter((label) => (filter === "overrides" ? label.override !== null : true))
      .filter((label) => needle === "" || label.source_type_raw.toLowerCase().includes(needle));
  }, [labels, query, filter]);
  const paged = usePagedList(filtered, PAGE_SIZE, `${parserType}|${query}|${filter}`);
  const overrides = labels.filter((label) => label.override !== null).length;
  const hasFilters = query.trim() !== "" || filter !== "all";

  return (
    <section className="flex flex-col gap-3">
      <p className="text-sm text-text-muted">
        {t("items.transactionTypes.page.summary", { count: labels.length, overrides })}
      </p>

      <div className="flex flex-wrap items-end gap-3">
        <div className="relative min-w-52 flex-1">
          <label htmlFor="labels-search" className="sr-only">
            {t("items.transactionTypes.page.search.label")}
          </label>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" aria-hidden="true" />
          <input
            id="labels-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("items.transactionTypes.page.search.placeholder", { count: labels.length })}
            className="w-full rounded-lg border border-border bg-surface py-2 pl-9 pr-3 text-sm text-text placeholder:text-text-muted"
          />
        </div>
        <div className="w-56">
          <Select
            label={t("items.transactionTypes.page.filter.label")}
            value={filter}
            onChange={(event) => setFilter(event.target.value as LabelFilter)}
          >
            <option value="all">{t("items.transactionTypes.page.filter.all")}</option>
            <option value="overrides">{t("items.transactionTypes.page.filter.overrides")}</option>
          </Select>
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="flex flex-col items-start gap-2 rounded-lg border border-border p-4">
          <p className="text-sm text-text-muted">{t("items.transactionTypes.page.noResults")}</p>
          {hasFilters && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setQuery("");
                setFilter("all");
              }}
            >
              {t("items.transactionTypes.page.clearFilters")}
            </Button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {paged.pageItems.map((label) => (
            <LabelRow key={label.source_type_raw} parserType={parserType} label={label} />
          ))}
        </div>
      )}

      <Pagination
        page={paged.page}
        pageCount={paged.pageCount}
        from={paged.from}
        to={paged.to}
        total={paged.total}
        onPageChange={paged.setPage}
      />
    </section>
  );
}

function LabelRow({ parserType, label }: { parserType: string; label: TransactionTypeLabel }) {
  const { t } = useTranslation(["settings", "common"]);
  const transactionTypeLabel = useTransactionTypeLabel();
  const upsert = useUpsertTransactionTypeMapping(parserType);
  const remove = useDeleteTransactionTypeMapping(parserType);
  const [selectedType, setSelectedType] = useState<TransactionType>(
    label.override ?? label.current_types[0]?.transaction_type ?? "expense",
  );
  const [resultMessage, setResultMessage] = useState<string | null>(null);

  const onSave = async () => {
    setResultMessage(null);
    const result = await upsert.mutateAsync({ sourceTypeRaw: label.source_type_raw, transactionType: selectedType });
    // Due frasi complete invece di un suffisso concatenato: il numero di
    // transazioni lasciate intatte cambia la struttura della frase, non solo
    // una coda appiccicata alla fine.
    setResultMessage(
      result.reapply.skipped > 0
        ? t("items.transactionTypes.page.reappliedWithSkipped", {
            count: result.reapply.updated,
            skipped: result.reapply.skipped,
          })
        : t("items.transactionTypes.page.reapplied", { count: result.reapply.updated }),
    );
  };

  const onRemove = async () => {
    setResultMessage(null);
    await remove.mutateAsync(label.source_type_raw);
  };

  const currentSummary = label.current_types
    .map((tc) => `${transactionTypeLabel(tc.transaction_type)} (${tc.count})`)
    .join(", ");

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-medium text-text">{label.source_type_raw}</p>
          <p className="text-sm text-text-muted">
            {t("items.transactionTypes.page.currentSummary", {
              count: label.total_count,
              summary: currentSummary,
            })}
          </p>
        </div>
        {label.override && <Badge tone="primary">{t("items.transactionTypes.page.overrideActive")}</Badge>}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={selectedType}
          onChange={(e) => setSelectedType(e.target.value as TransactionType)}
          aria-label={t("items.transactionTypes.page.typeFor", { label: label.source_type_raw })}
        >
          {TRANSACTION_TYPES.map((type) => (
            <option key={type} value={type}>
              {transactionTypeLabel(type)}
            </option>
          ))}
        </Select>
        <Button size="sm" loading={upsert.isPending} onClick={() => void onSave()}>
          {t("common:actions.save")}
        </Button>
        {label.override && (
          <Button size="sm" variant="ghost" loading={remove.isPending} onClick={() => void onRemove()}>
            {t("items.transactionTypes.page.removeOverride")}
          </Button>
        )}
      </div>

      {resultMessage && (
        <p role="status" className="text-sm text-success">
          {resultMessage}
        </p>
      )}
    </Card>
  );
}
