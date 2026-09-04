import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { Select } from "../../components/ui/Select";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { useAccounts } from "../accounts/api";
import { useCreateTaxLossOpening } from "./api";
import { useTaxIncomeCategoryLabel } from "./labels";

const AGGREGATE_SENTINEL = "__aggregate__";
const INCOME_CATEGORIES = ["redditi_diversi", "redditi_capitale"];

/** Dialog "Nuovo saldo di apertura" (SPEC_TAX_REGIME.md FETTA 1): il
 * perimetro e' un campo OBBLIGATORIO senza valore preselezionato (le fonti
 * si contraddicono su cosa succede alle minusvalenze passando da
 * dichiarativo ad amministrato, quindi Lumio non decide al posto
 * dell'utente) — il placeholder resta la selezione di default, mai un
 * perimetro gia' scelto. */
export function TaxLossOpeningDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation("tax");
  // Nessun filtro per account_type: un conto "checking" puo' comunque
  // essere un conto titoli in pratica (vedi AccountEditPage).
  const { data: accounts } = useAccounts();
  const incomeCategoryLabel = useTaxIncomeCategoryLabel();
  const create = useCreateTaxLossOpening();

  const [perimeter, setPerimeter] = useState("");
  const [formationDate, setFormationDate] = useState("");
  const [incomeCategory, setIncomeCategory] = useState("redditi_diversi");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setPerimeter("");
    setFormationDate("");
    setIncomeCategory("redditi_diversi");
    setAmount("");
    setError(null);
  };

  const onSave = async () => {
    setError(null);
    if (!perimeter) {
      setError(t("lossPocket.openingDialog.perimeterRequired"));
      return;
    }
    try {
      await create.mutateAsync({
        financial_account_id: perimeter === AGGREGATE_SENTINEL ? null : perimeter,
        formation_date: formationDate,
        income_category: incomeCategory,
        amount,
      });
      reset();
      onClose();
    } catch (err) {
      setError(friendlyErrorMessage(err, t("lossPocket.openingDialog.error")));
    }
  };

  return (
    <Dialog
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title={t("lossPocket.openingDialog.title")}
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Select
            label={t("lossPocket.openingDialog.perimeterLabel")}
            value={perimeter}
            onChange={(e) => setPerimeter(e.target.value)}
          >
            <option value="">{t("lossPocket.openingDialog.perimeterPlaceholder")}</option>
            <option value={AGGREGATE_SENTINEL}>{t("lossPocket.openingDialog.perimeterAggregateOption")}</option>
            {(accounts ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </Select>
          <p className="text-sm text-text-muted">{t("lossPocket.openingDialog.perimeterHint")}</p>
        </div>

        <Input
          type="date"
          label={t("lossPocket.openingDialog.formationDate")}
          value={formationDate}
          onChange={(e) => setFormationDate(e.target.value)}
        />

        <Select
          label={t("lossPocket.openingDialog.incomeCategory")}
          value={incomeCategory}
          onChange={(e) => setIncomeCategory(e.target.value)}
        >
          {INCOME_CATEGORIES.map((category) => (
            <option key={category} value={category}>
              {incomeCategoryLabel(category).label}
            </option>
          ))}
        </Select>

        <Input
          type="number"
          step="0.01"
          label={t("lossPocket.openingDialog.amount")}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />

        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              reset();
              onClose();
            }}
          >
            {t("lossPocket.openingDialog.cancel")}
          </Button>
          <Button loading={create.isPending} onClick={() => void onSave()}>
            {t("lossPocket.openingDialog.save")}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
