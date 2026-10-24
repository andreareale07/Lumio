import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Input } from "../../components/ui/Input";
import { friendlyErrorMessage } from "../../lib/errorMessage";
import { useExpireAsset } from "./api";

interface ExpireAssetDialogProps {
  open: boolean;
  onClose: () => void;
  assetId: string;
  assetLabel: string;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function ExpireAssetDialog({ open, onClose, assetId, assetLabel }: ExpireAssetDialogProps) {
  const { t } = useTranslation(["portfolio", "common"]);
  const expireAsset = useExpireAsset();
  const [expiryDate, setExpiryDate] = useState(todayIso());
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setExpiryDate(todayIso());
      setError(null);
    }
  }, [open]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!expiryDate) {
      setError(t("portfolio:corporateActions.expireDialog.validation.date"));
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await expireAsset.mutateAsync({ asset_id: assetId, expiry_date: expiryDate });
      onClose();
    } catch (failure) {
      setError(friendlyErrorMessage(failure, t("portfolio:corporateActions.expireDialog.error")));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} title={t("portfolio:corporateActions.expireDialog.title")}>
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <p className="text-sm text-text-muted">
          {t("portfolio:corporateActions.expireDialog.hint", { asset: assetLabel })}
        </p>
        <Input
          label={t("portfolio:corporateActions.expireDialog.fields.date")}
          type="date"
          value={expiryDate}
          onChange={(event) => setExpiryDate(event.target.value)}
        />
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <div className="mt-2 flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t("common:actions.cancel")}
          </Button>
          <Button type="submit" loading={submitting}>
            {t("portfolio:corporateActions.expireDialog.submit")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
