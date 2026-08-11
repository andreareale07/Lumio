import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "../../components/layout/AppShell";
import { AccountDetailPage } from "../../features/accounts/AccountDetailPage";
import { AccountsPage } from "../../features/accounts/AccountsPage";
import { ExpensesPage } from "../../features/analytics/ExpensesPage";
import { IncomePage } from "../../features/analytics/IncomePage";
import { NetWorthPage } from "../../features/analytics/NetWorthPage";
import { LoginPage } from "../../features/auth/LoginPage";
import { RegisterPage } from "../../features/auth/RegisterPage";
import { DashboardPage } from "../../features/dashboard/DashboardPage";
import { ImportsPage } from "../../features/imports/ImportsPage";
import { InvestmentsPage } from "../../features/portfolio/InvestmentsPage";
import { RulesPage } from "../../features/rules/RulesPage";
import { AISettingsPage } from "../../features/settings/ai/AISettingsPage";
import { MarketDataSettingsPage } from "../../features/settings/market-data/MarketDataSettingsPage";
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

      <Route path="/" element={<Protected><DashboardPage /></Protected>} />
      <Route path="/expenses" element={<Protected><ExpensesPage /></Protected>} />
      <Route path="/income" element={<Protected><IncomePage /></Protected>} />
      <Route path="/net-worth" element={<Protected><NetWorthPage /></Protected>} />
      <Route path="/investments" element={<Protected><InvestmentsPage /></Protected>} />
      <Route path="/accounts" element={<Protected><AccountsPage /></Protected>} />
      <Route path="/accounts/:accountId" element={<Protected><AccountDetailPage /></Protected>} />
      <Route path="/transactions" element={<Protected><TransactionsPage /></Protected>} />
      <Route path="/imports" element={<Protected><ImportsPage /></Protected>} />
      <Route path="/settings/rules" element={<Protected><RulesPage /></Protected>} />
      <Route path="/settings/ai" element={<Protected><AISettingsPage /></Protected>} />
      <Route path="/settings/market-data" element={<Protected><MarketDataSettingsPage /></Protected>} />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
