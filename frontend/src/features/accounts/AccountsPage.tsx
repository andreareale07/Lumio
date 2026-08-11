import { useState } from "react";
import { Landmark, Plus } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { Skeleton } from "../../components/ui/Skeleton";
import { useAccounts, useSetAccountActive } from "./api";
import { CreateAccountDialog } from "./CreateAccountDialog";
import { ACCOUNT_TYPE_LABELS } from "./labels";

export function AccountsPage() {
  const { data: accounts, isLoading, isError, refetch } = useAccounts();
  const setActive = useSetAccountActive();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-text">Conti</h1>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" /> Aggiungi conto
        </Button>
      </div>

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      )}

      {isError && <ErrorState message="Non siamo riusciti a caricare i tuoi conti." onRetry={() => void refetch()} />}

      {!isLoading && !isError && accounts && accounts.length === 0 && (
        <EmptyState
          icon={Landmark}
          title="Nessun conto"
          description="Aggiungi il tuo primo conto per iniziare a usare Lumio."
          action={<Button onClick={() => setCreateOpen(true)}>Aggiungi conto</Button>}
        />
      )}

      {!isLoading && !isError && accounts && accounts.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {accounts.map((account) => (
            <Card key={account.id} className="flex flex-col gap-2">
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-semibold text-text">{account.name}</p>
                  <p className="text-sm text-text-muted">{ACCOUNT_TYPE_LABELS[account.account_type]}</p>
                </div>
                {!account.is_active && <Badge tone="neutral">Archiviato</Badge>}
              </div>
              <div className="mt-2 flex items-center justify-between">
                <Link
                  to={`/transactions?account=${account.id}`}
                  className="text-sm font-medium text-primary hover:underline"
                >
                  Vedi movimenti
                </Link>
                <button
                  type="button"
                  onClick={() => setActive.mutate({ id: account.id, isActive: !account.is_active })}
                  className="text-sm text-text-muted hover:text-text"
                >
                  {account.is_active ? "Archivia" : "Riattiva"}
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <CreateAccountDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
