import { useState } from "react";
import { Bot, Plus, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "../../../components/ui/Badge";
import { Button } from "../../../components/ui/Button";
import { Card } from "../../../components/ui/Card";
import { Dialog } from "../../../components/ui/Dialog";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { SkeletonRows } from "../../../components/ui/Skeleton";
import type { AIProfile } from "../../../types/api";
import { useActivateAIProfile, useAIProfiles, useDeactivateAI, useDeleteAIProfile } from "./api";
import { AIProfileFormDialog } from "./AIProfileFormDialog";
import { aiProviderLabel } from "./schemas";

/** SPEC_FE §44-45: pagina `/settings/ai`. Piu' profili salvabili per
 * workspace, al massimo uno attivo (mutuamente esclusivo) — l'AI resta
 * sempre opzionale (SPEC §25): nessun profilo attivo, o nessun profilo
 * affatto, e' uno stato valido, non un errore. */
export function AISettingsPage() {
  const { t } = useTranslation(["settings", "common"]);
  const { data: profiles, isLoading, isError, refetch } = useAIProfiles();
  const activateProfile = useActivateAIProfile();
  const deactivateAI = useDeactivateAI();
  const deleteProfile = useDeleteAIProfile();

  const [formOpen, setFormOpen] = useState(false);
  const [editingProfile, setEditingProfile] = useState<AIProfile | null>(null);
  const [profileToDelete, setProfileToDelete] = useState<AIProfile | null>(null);

  const openCreate = () => {
    setEditingProfile(null);
    setFormOpen(true);
  };
  const openEdit = (profile: AIProfile) => {
    setEditingProfile(profile);
    setFormOpen(true);
  };

  const activeProfile = profiles?.find((p) => p.is_active) ?? null;

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-text">{t("items.ai.label")}</h1>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4" /> {t("items.ai.page.newProfile")}
        </Button>
      </div>

      <p className="text-sm text-text-muted">{t("items.ai.pageDescription")}</p>

      {isLoading && <SkeletonRows rows={3} />}
      {isError && <ErrorState message={t("items.ai.page.loadError")} onRetry={() => void refetch()} />}

      {!isLoading && !isError && profiles && profiles.length === 0 && (
        <EmptyState
          icon={Sparkles}
          title={t("items.ai.page.empty.title")}
          description={t("items.ai.page.empty.description")}
          action={<Button onClick={openCreate}>{t("items.ai.page.newProfile")}</Button>}
        />
      )}

      {!isLoading && !isError && profiles && profiles.length > 0 && (
        <div className="flex flex-col gap-2">
          {profiles.map((profile) => (
            <Card key={profile.id} className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <Bot className="h-5 w-5 text-text-muted" aria-hidden="true" />
                <div>
                  <p className="font-medium text-text">{profile.name}</p>
                  <p className="text-sm text-text-muted">
                    {aiProviderLabel(t, profile.provider)}
                    {profile.model ? ` · ${profile.model}` : ""}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {profile.is_active && <Badge tone="success">{t("items.ai.page.active")}</Badge>}
                {profile.is_active ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={deactivateAI.isPending}
                    onClick={() => deactivateAI.mutate()}
                  >
                    {t("items.ai.page.deactivate")}
                  </Button>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={activateProfile.isPending}
                    onClick={() => activateProfile.mutate(profile.id)}
                  >
                    {t("items.ai.page.activate")}
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={() => openEdit(profile)}>
                  {t("items.ai.page.edit")}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => setProfileToDelete(profile)}>
                  {t("items.ai.page.delete")}
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <AIProfileFormDialog open={formOpen} onClose={() => setFormOpen(false)} profile={editingProfile} />

      <Dialog
        open={!!profileToDelete}
        onClose={() => setProfileToDelete(null)}
        title={t("items.ai.page.deleteDialog.title")}
      >
        <p className="text-sm text-text-muted">
          {t("items.ai.page.deleteDialog.body", { name: profileToDelete?.name })}
          {profileToDelete?.is_active && ` ${t("items.ai.page.deleteDialog.activeWarning")}`}
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
            {t("items.ai.page.delete")}
          </Button>
        </div>
      </Dialog>

      {!activeProfile && profiles && profiles.length > 0 && (
        <p className="text-sm text-text-muted">{t("items.ai.page.noActiveProfile")}</p>
      )}
    </div>
  );
}
