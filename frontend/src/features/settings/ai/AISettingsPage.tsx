import { useState } from "react";
import { Bot, Plus, Sparkles } from "lucide-react";

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
import { AI_PROVIDER_LABELS } from "./schemas";

/** SPEC_FE §44-45: pagina `/settings/ai`. Piu' profili salvabili per
 * workspace, al massimo uno attivo (mutuamente esclusivo) — l'AI resta
 * sempre opzionale (SPEC §25): nessun profilo attivo, o nessun profilo
 * affatto, e' uno stato valido, non un errore. */
export function AISettingsPage() {
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
        <h1 className="text-lg font-semibold text-text">AI</h1>
        <Button size="sm" onClick={openCreate}>
          <Plus className="h-4 w-4" /> Nuovo profilo
        </Button>
      </div>

      <p className="text-sm text-text-muted">
        L'AI è opzionale: le transazioni vengono comunque classificate dalle regole anche senza un profilo
        attivo. Puoi salvare più profili (anche dello stesso provider) e attivarne uno alla volta.
      </p>

      {isLoading && <SkeletonRows rows={3} />}
      {isError && (
        <ErrorState message="Non siamo riusciti a caricare i profili AI." onRetry={() => void refetch()} />
      )}

      {!isLoading && !isError && profiles && profiles.length === 0 && (
        <EmptyState
          icon={Sparkles}
          title="Nessun profilo AI"
          description="Crea un profilo per classificare automaticamente le transazioni che le regole non riconoscono."
          action={<Button onClick={openCreate}>Nuovo profilo</Button>}
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
                    {AI_PROVIDER_LABELS[profile.provider]}
                    {profile.model ? ` · ${profile.model}` : ""}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {profile.is_active && <Badge tone="success">Attivo</Badge>}
                {profile.is_active ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={deactivateAI.isPending}
                    onClick={() => deactivateAI.mutate()}
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

      <AIProfileFormDialog open={formOpen} onClose={() => setFormOpen(false)} profile={editingProfile} />

      <Dialog open={!!profileToDelete} onClose={() => setProfileToDelete(null)} title="Eliminare il profilo?">
        <p className="text-sm text-text-muted">
          "{profileToDelete?.name}" verrà eliminato definitivamente.
          {profileToDelete?.is_active && " È il profilo attivo: dopo l'eliminazione l'AI resterà disabilitata."}
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
        <p className="text-sm text-text-muted">Nessun profilo attivo: l'AI è disabilitata.</p>
      )}
    </div>
  );
}
