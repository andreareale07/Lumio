import { useState } from "react";
import { LineChart, Plus, RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Dialog } from "../../../components/ui/Dialog";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { SkeletonRows } from "../../../components/ui/Skeleton";
import type { MarketDataProfile } from "../../../types/api";
import {
  useActivateMarketDataProfile,
  useDeactivateMarketData,
  useDeleteMarketDataProfile,
  useMarketDataProfiles,
  useTriggerMarketDataRefresh,
} from "./api";
import { MarketDataProfileFormDialog } from "./MarketDataProfileFormDialog";
import { MARKET_DATA_PROVIDER_LABELS } from "./schemas";

/** SPEC §38: pagina `/settings/market-data`. Il market data resta sempre
 * opzionale (DoD M09: "l'app funziona anche senza provider configurato") —
 * nessun profilo attivo, o nessun profilo affatto, e' uno stato valido: le
 * posizioni restano valorizzate al costo storico, non e' un errore. */
export function MarketDataSettingsPage() {
  const { data: profiles, isLoading, isError, refetch } = useMarketDataProfiles();
  const activateProfile = useActivateMarketDataProfile();
  const deactivateMarketData = useDeactivateMarketData();
  const deleteProfile = useDeleteMarketDataProfile();
  const triggerRefresh = useTriggerMarketDataRefresh();
  const queryClient = useQueryClient();

  const [formOpen, setFormOpen] = useState(false);
  const [editingProfile, setEditingProfile] = useState<MarketDataProfile | null>(null);
  const [profileToDelete, setProfileToDelete] = useState<MarketDataProfile | null>(null);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);

  const openCreate = () => {
    setEditingProfile(null);
    setFormOpen(true);
  };
  const openEdit = (profile: MarketDataProfile) => {
    setEditingProfile(profile);
    setFormOpen(true);
  };

  const activeProfile = profiles?.find((p) => p.is_active) ?? null;

  const onRefreshNow = async () => {
    setRefreshMessage(null);
    await triggerRefresh.mutateAsync();
    setRefreshMessage("Aggiornamento avviato in background. I nuovi prezzi appariranno a breve.");
    // Nessun canale di progresso live per questo job (vedi backend,
    // MarketDataRefreshTriggered): si invalidano le query dei prezzi/
    // posizioni dopo un breve ritardo, cosi' un refetch mostra i dati
    // aggiornati senza che l'utente debba ricaricare la pagina a mano.
    setTimeout(() => {
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
    }, 4000);
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-text">Market Data</h1>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4" /> Nuovo profilo
        </Button>
      </div>

      <p className="text-sm text-text-muted">
        Il market data è opzionale: senza un provider attivo le posizioni restano valorizzate al costo
        storico, senza errori. Puoi salvare più profili e attivarne uno alla volta.
      </p>

      {isLoading && <SkeletonRows rows={3} />}
      {isError && (
        <ErrorState message="Non siamo riusciti a caricare i profili." onRetry={() => void refetch()} />
      )}

      {!isLoading && !isError && profiles && profiles.length === 0 && (
        <EmptyState
          icon={LineChart}
          title="Nessun profilo market data"
          description="Crea un profilo per valorizzare le tue posizioni a prezzo di mercato invece che a costo storico."
          action={<Button onClick={openCreate}>Nuovo profilo</Button>}
        />
      )}

      {!isLoading && !isError && profiles && profiles.length > 0 && (
        <div className="flex flex-col gap-2">
          {profiles.map((profile) => (
            <Card key={profile.id} className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <LineChart className="h-5 w-5 text-text-muted" aria-hidden="true" />
                <div>
                  <p className="font-medium text-text">{profile.name}</p>
                  <p className="text-sm text-text-muted">{MARKET_DATA_PROVIDER_LABELS[profile.provider]}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {profile.is_active && <Badge tone="success">Attivo</Badge>}
                {profile.is_active ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={deactivateMarketData.isPending}
                    onClick={() => deactivateMarketData.mutate()}
                  >
                    Disattiva
                  </Button>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={activateProfile.isPending}
                    onClick={() => activateProfile.mutate(profile.id)}
                  >
                    Attiva
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => openEdit(profile)}>
                  Modifica
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setProfileToDelete(profile)}>
                  Elimina
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {activeProfile && activeProfile.provider !== "manual" && (
        <Card className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-medium text-text">Aggiornamento prezzi</p>
            <p className="text-sm text-text-muted">
              Avviene automaticamente ogni notte. Puoi anche avviarlo subito.
            </p>
          </div>
          <Button variant="secondary" size="sm" loading={triggerRefresh.isPending} onClick={() => void onRefreshNow()}>
            <RefreshCw className="h-4 w-4" /> Aggiorna prezzi ora
          </Button>
        </Card>
      )}
      {refreshMessage && (
        <p role="status" className="text-sm text-success">
          {refreshMessage}
        </p>
      )}

      <MarketDataProfileFormDialog open={formOpen} onClose={() => setFormOpen(false)} profile={editingProfile} />

      <Dialog open={!!profileToDelete} onClose={() => setProfileToDelete(null)} title="Eliminare il profilo?">
        <p className="text-sm text-text-muted">
          "{profileToDelete?.name}" verrà eliminato definitivamente.
          {profileToDelete?.is_active &&
            " È il profilo attivo: dopo l'eliminazione il market data resterà disabilitato."}
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setProfileToDelete(null)}>
            Annulla
          </Button>
          <Button
            variant="danger"
            onClick={async () => {
              if (profileToDelete) await deleteProfile.mutateAsync(profileToDelete.id);
              setProfileToDelete(null);
            }}
          >
            Elimina
          </Button>
        </div>
      </Dialog>

      {!activeProfile && profiles && profiles.length > 0 && (
        <p className="text-sm text-text-muted">Nessun profilo attivo: valorizzazione a costo storico.</p>
      )}
    </div>
  );
}
