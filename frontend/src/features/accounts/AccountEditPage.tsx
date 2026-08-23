import { Landmark } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { BackLink } from "../../components/ui/BackLink";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LinkButton } from "../../components/ui/LinkButton";
import { SkeletonRows } from "../../components/ui/Skeleton";
import { useAccounts } from "./api";
import { AccountForm, IbanHistorySection } from "./AccountForm";

/** Pagina dedicata (richiesta esplicita dell'utente, invece del dialog
 * stretto usato per la creazione): serve spazio per lo storico IBAN in
 * fondo, che in un dialog risultava compresso. La creazione di un nuovo
 * conto resta un dialog rapido — `AccountFormDialog` — nessuno storico da
 * mostrare per un conto che non esiste ancora. */
export function AccountEditPage() {
  const { t } = useTranslation("accounts");
  const navigate = useNavigate();
  const { accountId } = useParams<{ accountId: string }>();
  const { data: accounts, isLoading, isError, refetch } = useAccounts();
  const account = accounts?.find((a) => a.id === accountId);

  if (isLoading) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <SkeletonRows rows={5} />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <ErrorState message={t("detail.loadError")} onRetry={() => void refetch()} />
      </div>
    );
  }

  if (!account) {
    return (
      <div className="mx-auto flex max-w-2xl flex-col gap-4">
        <EmptyState
          icon={Landmark}
          title={t("detail.notFound.title")}
          description={t("detail.notFound.description")}
          action={<LinkButton to="/accounts">{t("detail.notFound.action")}</LinkButton>}
        />
      </div>
    );
  }

  const backTo = `/accounts/${account.id}`;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div>
        <BackLink to={backTo} label={account.name} />
        <h1 className="mt-1 text-lg font-semibold text-text">{t("form.editTitle")}</h1>
      </div>
      <Card>
        <AccountForm account={account} onSaved={() => navigate(backTo)} onCancel={() => navigate(backTo)} />
      </Card>
      <Card>
        <IbanHistorySection accountId={account.id} />
      </Card>
    </div>
  );
}
