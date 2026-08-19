import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../providers/AuthProvider";

/** SPEC_FE §75: route protette -> redirect a /login se non autenticato. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  const { t } = useTranslation("common");

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg text-text-muted">
        {t("loading")}
      </div>
    );
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <>{children}</>;
}
