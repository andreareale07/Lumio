import { Check, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { formatDate, formatSignedMoney } from "../../lib/format";
import type { ImportRecord } from "../../types/api";
import { type DuplicateReviewItem, useDecideImportReviewItem, useImportReviewItems } from "./api";

interface DuplicateReviewDrawerProps {
  importRecord: ImportRecord | null;
  onClose: () => void;
}

/** SPEC §15/§16: quando il Deduplication Engine trova un candidato ambiguo
 * (stesso conto/data/importo/currency/tipo, descrizione diversa) l'import
 * resta in 'ready_for_review' finche' l'utente non decide, voce per voce,
 * se e' davvero un movimento diverso ("IMPORTA COMUNQUE") o lo stesso
 * movimento gia' presente ("NON IMPORTARE") — mai una decisione automatica
 * su un match incerto (SPEC §14). */
export function DuplicateReviewDrawer({ importRecord, onClose }: DuplicateReviewDrawerProps) {
  const { t } = useTranslation(["imports", "common"]);
  const importId = importRecord?.id ?? null;
  const { data: items, isLoading } = useImportReviewItems(importId, "pending");
  const decide = useDecideImportReviewItem(importId);

  const handleDecision = (itemId: string, decision: "keep_new" | "mark_duplicate") => {
    decide.mutate({ itemId, decision });
  };

  return (
    <Dialog
      open={!!importRecord}
      onClose={onClose}
      title={t("duplicateReview.title", { filename: importRecord?.filename ?? "" })}
    >
      <div className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto">
        {isLoading && <p className="text-sm text-text-muted">{t("common:loading")}</p>}

        {!isLoading && items && items.length === 0 && (
          <EmptyState
            icon={Check}
            title={t("duplicateReview.empty.title")}
            description={t("duplicateReview.empty.description")}
          />
        )}

        {decide.isError && (
          <p role="alert" className="text-sm text-danger">
            {friendlyErrorMessage(decide.error, t("duplicateReview.decideError"))}
          </p>
        )}

        {!isLoading &&
          items?.map((item) => (
            <ReviewItemCard
              key={item.id}
              item={item}
              onKeepNew={() => handleDecision(item.id, "keep_new")}
              onMarkDuplicate={() => handleDecision(item.id, "mark_duplicate")}
              pending={decide.isPending}
            />
          ))}
      </div>

      <div className="mt-4 flex justify-end">
        <Button variant="secondary" onClick={onClose}>
          {t("common:actions.close")}
        </Button>
      </div>
    </Dialog>
  );
}

function ReviewItemCard({
  item,
  onKeepNew,
  onMarkDuplicate,
  pending,
}: {
  item: DuplicateReviewItem;
  onKeepNew: () => void;
  onMarkDuplicate: () => void;
  pending: boolean;
}) {
  const { t } = useTranslation("imports");
  return (
    <Card className="flex flex-col gap-3">
      <Badge tone="warning">{t("duplicateReview.possibleDuplicateBadge")}</Badge>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TransactionSummary
          label={t("duplicateReview.newTransaction")}
          date={item.transaction_date}
          description={item.description_raw}
          amount={item.amount}
          currency={item.currency}
          transactionType={item.transaction_type}
          balanceAfter={item.balance_after}
        />
        {item.candidate && (
          <TransactionSummary
            label={t("duplicateReview.existingTransaction")}
            date={item.candidate.transaction_date}
            description={item.candidate.description_raw}
            amount={item.candidate.amount}
            currency={item.candidate.currency}
            transactionType={item.candidate.transaction_type}
            balanceAfter={item.candidate.balance_after}
          />
        )}
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="secondary" size="sm" onClick={onMarkDuplicate} disabled={pending}>
          <X className="h-4 w-4" /> {t("duplicateReview.markDuplicate")}
        </Button>
        <Button size="sm" onClick={onKeepNew} disabled={pending}>
          <Check className="h-4 w-4" /> {t("duplicateReview.keepNew")}
        </Button>
      </div>
    </Card>
  );
}

function TransactionSummary({
  label,
  date,
  description,
  amount,
  currency,
  transactionType,
  balanceAfter,
}: {
  label: string;
  date: string;
  description: string;
  amount: string;
  currency: string;
  transactionType: string;
  balanceAfter: string | null;
}) {
  const { t } = useTranslation("imports");
  return (
    <div className="rounded-lg border border-border p-3 text-sm">
      <p className="mb-1 font-medium text-text-muted">{label}</p>
      <p className="text-text-muted">{formatDate(date)}</p>
      <p className="text-text">{description}</p>
      <p className="font-medium text-text">{formatSignedMoney(amount, currency)}</p>
      <p className="text-xs text-text-muted">{transactionType}</p>
      {balanceAfter !== null && (
        <p className="text-xs text-text-muted">
          {t("duplicateReview.balanceAfter", { value: formatSignedMoney(balanceAfter, currency) })}
        </p>
      )}
    </div>
  );
}
