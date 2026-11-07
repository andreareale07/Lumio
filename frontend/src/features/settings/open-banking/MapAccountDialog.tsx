import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "../../../components/ui/Button";
import { Dialog } from "../../../components/ui/Dialog";
import { Select } from "../../../components/ui/Select";
import { friendlyErrorMessage } from "../../../lib/errorMessage";
import { useAccounts } from "../../accounts/api";
import type { BankConnectionAccount, Uuid } from "../../../types/api";
import { useUpdateBankAccount } from "./api";

const CREATE_NEW = "__new__";

interface Props {
  connectionId: Uuid;
  account: BankConnectionAccount | null;
  onClose: () => void;
}

/** Abbina un conto della banca a un conto Lumio (nuovo o esistente) e ne attiva
 * l'importazione. Mai un abbinamento automatico, neanche con IBAN uguale: si
 * propone e l'utente conferma (regola del progetto). */
export function MapAccountDialog({ connectionId, account, onClose }: Props) {
  const { t } = useTranslation("settings");
  const accounts = useAccounts();
  const update = useUpdateBankAccount();
  const [choice, setChoice] = useState(CREATE_NEW);
  const [error, setError] = useState<string | null>(null);

  if (!account) return null;

  const label = account.name ?? account.product ?? account.iban_masked ?? "";
  // Prima i conti con la stessa valuta e, se coincide, lo stesso IBAN: sono i candidati piu' probabili.
  const candidates = [...(accounts.data ?? [])].sort((a, b) => {
    const score = (c: { currency: string }) => (c.currency === account.currency ? 0 : 1);
    return score(a) - score(b);
  });

  const submit = async () => {
    setError(null);
    try {
      await update.mutateAsync({
        connectionId,
        accountId: account.id,
        update: choice === CREATE_NEW ? { create_account: true } : { financial_account_id: choice },
      });
      await update.mutateAsync({ connectionId, accountId: account.id, update: { enabled: true } });
      onClose();
    } catch (e) {
      setError(friendlyErrorMessage(e, t("items.bankConnections.page.mapDialog.saveError")));
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title={t("items.bankConnections.page.mapDialog.title", { name: label })}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} className="flex-1 sm:flex-none">
            {t("items.bankConnections.page.mapDialog.cancel")}
          </Button>
          <Button onClick={() => void submit()} loading={update.isPending} className="flex-1 sm:flex-none">
            {t("items.bankConnections.page.mapDialog.save")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-sm text-text-muted">{t("items.bankConnections.page.mapDialog.description")}</p>
        <Select
          label={t("items.bankConnections.page.mapDialog.select")}
          value={choice}
          onChange={(event) => setChoice(event.target.value)}
        >
          <option value={CREATE_NEW}>{t("items.bankConnections.page.mapDialog.createNew")}</option>
          {candidates.length > 0 && (
            <optgroup label={t("items.bankConnections.page.mapDialog.existingGroup")}>
              {candidates.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.name} ({candidate.currency})
                </option>
              ))}
            </optgroup>
          )}
        </Select>
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
      </div>
    </Dialog>
  );
}
