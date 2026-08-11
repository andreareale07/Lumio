import { useMemo, useState } from "react";
import { Wand2 } from "lucide-react";

import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Skeleton } from "../../components/ui/Skeleton";
import { CategoryPicker } from "../categories/CategoryPicker";
import { useCategories } from "../categories/api";
import { categoryLabel } from "../categories/utils";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { formatDateTime, formatSignedMoney } from "../../lib/format";
import { RuleFormDialog, type RuleDialogDefaults } from "../rules/RuleFormDialog";
import { useRuleSuggestions } from "../rules/api";
import type { Transaction } from "../../types/api";
import { ClassificationIndicator } from "./ClassificationIndicator";
import { useClassifications, useUpdateTransactionCategory } from "./api";

export function TransactionDetailDrawer({
  transaction,
  onClose,
}: {
  transaction: Transaction | null;
  onClose: () => void;
}) {
  const { data: categories } = useCategories();
  const { data: classifications, isLoading: classificationsLoading } = useClassifications(
    transaction?.id ?? null,
  );
  const updateCategory = useUpdateTransactionCategory();
  const { data: suggestions } = useRuleSuggestions();
  const [categoryError, setCategoryError] = useState<string | null>(null);
  const [ruleDialogDefaults, setRuleDialogDefaults] = useState<RuleDialogDefaults | null>(null);

  const latestClassification = classifications?.[0] ?? null;

  const matchingSuggestion = useMemo(() => {
    if (!transaction || !suggestions) return null;
    return suggestions.find((s) => s.transaction_ids.includes(transaction.id)) ?? null;
  }, [transaction, suggestions]);

  if (!transaction) return null;

  const onCategoryChange = async (categoryId: string) => {
    setCategoryError(null);
    try {
      await updateCategory.mutateAsync({ id: transaction.id, categoryId: categoryId || null });
    } catch (error) {
      setCategoryError(friendlyErrorMessage(error, "Non è stato possibile aggiornare la categoria."));
    }
  };

  const openRuleDialogFromTransaction = () => {
    setRuleDialogDefaults({
      name: transaction.merchant ?? transaction.description_raw,
      field: "description",
      operator: "contains",
      value: transaction.description_normalized ?? transaction.description_raw,
      category_id: transaction.category_id ?? undefined,
    });
  };

  const openRuleDialogFromSuggestion = () => {
    if (!matchingSuggestion) return;
    setRuleDialogDefaults({
      name: matchingSuggestion.match_value,
      field: matchingSuggestion.match_field,
      operator: matchingSuggestion.match_field === "merchant" ? "merchant_equals" : "contains",
      value: matchingSuggestion.match_value,
      category_id: matchingSuggestion.category_id,
    });
  };

  return (
    <>
      <Drawer open={!!transaction} onClose={onClose} title={transaction.merchant ?? transaction.description_raw}>
        <div className="flex flex-col gap-5">
          <div>
            <p className={`font-numeric text-2xl font-semibold ${Number(transaction.amount) < 0 ? "text-text" : "text-success"}`}>
              {formatSignedMoney(transaction.amount, transaction.currency)}
            </p>
            <p className="text-sm text-text-muted">{formatDateTime(transaction.transaction_date)}</p>
          </div>

          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-text-muted">Tipo</dt>
            <dd className="text-text">{transaction.transaction_type}</dd>
            <dt className="text-text-muted">Descrizione originale</dt>
            <dd className="col-span-2 text-text">{transaction.description_raw}</dd>
          </dl>

          <div>
            <p className="mb-1.5 text-sm font-medium text-text">Categoria</p>
            <CategoryPicker
              includeEmptyOption
              value={transaction.category_id ?? ""}
              onChange={(e) => void onCategoryChange(e.target.value)}
              error={categoryError ?? undefined}
              disabled={updateCategory.isPending}
            />
          </div>

          <div>
            <p className="mb-1.5 text-sm font-medium text-text">Classificazione</p>
            {classificationsLoading ? (
              <Skeleton className="h-6 w-24" />
            ) : (
              <ClassificationIndicator classification={latestClassification} />
            )}
          </div>

          {matchingSuggestion && (
            <div className="rounded-lg border border-primary/30 bg-primary/5 p-3">
              <p className="flex items-center gap-1.5 text-sm font-medium text-text">
                <Wand2 className="h-4 w-4 text-primary" /> Hai classificato "{matchingSuggestion.match_value}" come{" "}
                {categoryLabel(categories, matchingSuggestion.category_id)} {matchingSuggestion.occurrences} volte.
              </p>
              <p className="mb-2 text-sm text-text-muted">Vuoi applicare questa scelta anche ai prossimi movimenti?</p>
              <Button size="sm" onClick={openRuleDialogFromSuggestion}>
                Crea regola
              </Button>
            </div>
          )}

          <Button variant="secondary" size="sm" onClick={openRuleDialogFromTransaction} className="self-start">
            <Wand2 className="h-4 w-4" /> Crea regola da questa transazione
          </Button>

          {classifications && classifications.length > 0 && (
            <div>
              <p className="mb-1.5 text-sm font-medium text-text">Storico classificazioni</p>
              <ul className="flex flex-col gap-2">
                {classifications.map((c) => (
                  <li key={c.id} className="flex items-center justify-between rounded-lg border border-border p-2 text-sm">
                    <div className="flex items-center gap-2">
                      <ClassificationIndicator classification={c} />
                      <span className="text-text-muted">{categoryLabel(categories, c.category_id)}</span>
                    </div>
                    <span className="text-text-muted">{formatDateTime(c.created_at)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </Drawer>

      <RuleFormDialog
        open={!!ruleDialogDefaults}
        onClose={() => setRuleDialogDefaults(null)}
        defaults={ruleDialogDefaults ?? undefined}
      />
    </>
  );
}
