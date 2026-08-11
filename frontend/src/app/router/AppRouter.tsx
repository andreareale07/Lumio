import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "../../components/layout/AppShell";
import { AccountsPage } from "../../features/accounts/AccountsPage";
import { LoginPage } from "../../features/auth/LoginPage";
import { RegisterPage } from "../../features/auth/RegisterPage";
import { ImportsPage } from "../../features/imports/ImportsPage";
import { RulesPage } from "../../features/rules/RulesPage";
import { AISettingsPage } from "../../features/settings/ai/AISettingsPage";
import { TransactionsPage } from "../../features/transactions/TransactionsPage";
import { RequireAuth } from "./RequireAuth";

function Protected({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>{children}</AppShell>
    </RequireAuth>
  );
}

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route path="/accounts" element={<Protected><AccountsPage /></Protected>} />
      <Route path="/transactions" element={<Protected><TransactionsPage /></Protected>} />
      <Route path="/imports" element={<Protected><ImportsPage /></Protected>} />
      <Route path="/settings/rules" element={<Protected><RulesPage /></Protected>} />
      <Route path="/settings/ai" element={<Protected><AISettingsPage /></Protected>} />

      <Route path="/" element={<Navigate to="/accounts" replace />} />
      <Route path="*" element={<Navigate to="/accounts" replace />} />
    </Routes>
  );
}
