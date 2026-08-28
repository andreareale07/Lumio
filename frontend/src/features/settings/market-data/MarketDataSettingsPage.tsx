import { useState } from "react";
import { LineChart, Plus, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";

import { usePageToolbar } from "../../../components/layout/PageToolbarContext";
import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Dialog } from "../../../components/ui/Dialog";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { JobRunStatus } from "../../../components/ui/JobRunStatus";
import { SkeletonRows } from "../../../components/ui/Skeleton";
import type { MarketDataProfile } from "../../../types/api";
import {
  useActivateMarketDataProfile,
  useDeactivateMarketData,
  useDeleteMarketDataProfile,
  useMarketDataProfiles,
  useMarketDataRefreshStatus,
  useTriggerMarketDataRefresh,
} from "./api";
import { MarketDataProfileFormDialog } from "./MarketDataProfileFormDialog";
import { marketDataProviderLabel } from "./schemas";

/** SPEC §38: pagina `/settings/market-data`. Il market data resta sempre
 * opzionale (DoD M09: "l'app funziona anche senza provider configurato") —
 * nessun profilo attivo, o nessun profilo affatto, e' uno stato valido: le
 * posizioni restano valorizzate al costo storico, non e' un errore. */
export function MarketDataSettingsPage() {
  const { t } = useTranslation(["settings", "common"]);
  const { data: profiles, isLoading, isError, refetch } = useMarketDataProfiles();
  const activateProfile = useActivateMarketDataProfile();
  const deactivateMarketData = useDeactivateMarketData();
  const deleteProfile = useDeleteMarketDataProfile();
  const triggerRefresh = useTriggerMarketDataRefresh();
  const refreshStatus = useMarketDataRefreshStatus();
  const queryClient = useQueryClient();

  const [formOpen, setFormOpen] = useState(false);
  const [editingProfile, setEditingProfile] = useState<MarketDataProfile | null>(null);
  const [profileToDelete, setProfileToDelete] = useState<MarketDataProfile | null>(null);

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
    await triggerRefresh.mutateAsync();
    // Nessun canale di progresso live per questo job (vedi backend,
    // MarketDataRefreshTriggered): dopo un breve ritardo (il tempo che il
    // worker prenda in carico il job e scriva "running") si ri-legge lo
    // stato persistente (JobRunStatus, sopravvive a un refresh pagina) e
    // si invalidano le query dei prezzi/posizioni.
    setTimeout(() => {
      queryClient.invalidateQueries({ queryKey: ["portfolio"] });
      void refreshStatus.refetch();
    }, 1500);
  };

  const newProfileButton = (
    <Button size="sm" onClick={openCreate}>
      <Plus className="h-4 w-4" /> {t("items.marketData.page.newProfile")}
    </Button>
  );
  const toolbarPortal = usePageToolbar(newProfileButton);

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      {toolbarPortal}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-text">{t("items.marketData.label")}</h1>
        <div className="md:hidden">{newProfileButton}</div>
      </div>

      <p className="text-sm text-text-muted">{t("items.marketData.page.intro")}</p>

      {isLoading && <SkeletonRows rows={3} />}
      {isError && <ErrorState message={t("items.marketData.page.loadError")} onRetry={() => void refetch()} />}

      {!isLoading && !isError && profiles && profiles.length === 0 && (
        <EmptyState
          icon={LineChart}
          title={t("items.marketData.page.empty.title")}
          description={t("items.marketData.page.empty.description")}
          action={<Button onClick={openCreate}>{t("items.marketData.page.newProfile")}</Button>}
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
                  <p className="text-sm text-text-muted">{marketDataProviderLabel(t, profile.provider)}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {profile.is_active && <Badge tone="success">{t("items.marketData.page.active")}</Badge>}
                {profile.is_active ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={deactivateMarketData.isPending}
                    onClick={() => deactivateMarketData.mutate()}
                  >
                    {t("items.marketData.page.deactivate")}
                  </Button>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={activateProfile.isPending}
                    onClick={() => activateProfile.mutate(profile.id)}
                  >
                    {t("items.marketData.page.activate")}
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => openEdit(profile)}>
                  {t("items.marketData.page.edit")}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setProfileToDelete(profile)}>
                  {t("items.marketData.page.delete")}
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {activeProfile && activeProfile.provider !== "manual" && (
        <Card className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-medium text-text">{t("items.marketData.page.refresh.title")}</p>
            <p className="text-sm text-text-muted">{t("items.marketData.page.refresh.description")}</p>
          </div>
          <Button variant="secondary" size="sm" loading={triggerRefresh.isPending} onClick={() => void onRefreshNow()}>
            <RefreshCw className="h-4 w-4" /> {t("items.marketData.page.refresh.action")}
          </Button>
        </Card>
      )}
      <JobRunStatus run={refreshStatus.data} />

      <MarketDataProfileFormDialog open={formOpen} onClose={() => setFormOpen(false)} profile={editingProfile} />

      <Dialog
        open={!!profileToDelete}
        onClose={() => setProfileToDelete(null)}
        title={t("items.marketData.page.deleteDialog.title")}
      >
        <p className="text-sm text-text-muted">
          {t("items.marketData.page.deleteDialog.body", { name: profileToDelete?.name })}
          {profileToDelete?.is_active && ` ${t("items.marketData.page.deleteDialog.activeWarning")}`}
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setProfileToDelete(null)}>
            {t("common:actions.cancel")}
          </Button>
          <Button
            variant="danger"
            onClick={async () => {
              if (profileToDelete) await deleteProfile.mutateAsync(profileToDelete.id);
              setProfileToDelete(null);
            }}
          >
            {t("items.marketData.page.delete")}
          </Button>
        </div>
      </Dialog>

      {!activeProfile && profiles && profiles.length > 0 && (
        <p className="text-sm text-text-muted">{t("items.marketData.page.noActiveProfile")}</p>
      )}
    </div>
  );
}
