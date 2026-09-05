import type { ReactNode } from "react";
import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { AppShell } from "../../components/layout/AppShell";
import { SettingsLayout } from "../../components/layout/SettingsLayout";
import { AccountDetailPage } from "../../features/accounts/AccountDetailPage";
import { AccountEditPage } from "../../features/accounts/AccountEditPage";
import { AccountsPage } from "../../features/accounts/AccountsPage";
import { ActivityPage } from "../../features/activity/ActivityPage";
import { ExpensesPage } from "../../features/analytics/ExpensesPage";
import { IncomePage } from "../../features/analytics/IncomePage";
import { NetWorthPage } from "../../features/analytics/NetWorthPage";
import { LoginPage } from "../../features/auth/LoginPage";
import { CategoriesSettingsPage } from "../../features/categories/CategoriesSettingsPage";
import { RegisterPage } from "../../features/auth/RegisterPage";
import { DashboardPage } from "../../features/dashboard/DashboardPage";
import { ImportsPage } from "../../features/imports/ImportsPage";
import { AssetDetailPage } from "../../features/portfolio/AssetDetailPage";
import { InvestmentsOverviewPage } from "../../features/portfolio/InvestmentsOverviewPage";
import { PortfolioDetailPage } from "../../features/portfolio/PortfolioDetailPage";
import { RulesPage } from "../../features/rules/RulesPage";
import { AISettingsPage } from "../../features/settings/ai/AISettingsPage";
import { CurrencySettingsPage } from "../../features/settings/currency/CurrencySettingsPage";
import { IntegrationsSettingsPage } from "../../features/settings/integrations/IntegrationsSettingsPage";
import { JobsSettingsPage } from "../../features/settings/jobs/JobsSettingsPage";
import { MarketDataSettingsPage } from "../../features/settings/market-data/MarketDataSettingsPage";
import { SettingsHubPage } from "../../features/settings/SettingsHubPage";
import { TaxSettingsPage } from "../../features/settings/tax/TaxSettingsPage";
import { TaxLossPocketPage } from "../../features/tax/TaxLossPocketPage";
import { TaxRealizedEventsPage } from "../../features/tax/TaxRealizedEventsPage";
import { TransactionTypeMappingsPage } from "../../features/settings/transaction-types/TransactionTypeMappingsPage";
import { TransactionsPage } from "../../features/transactions/TransactionsPage";
import { useAuth } from "../providers/AuthProvider";
import { RequireAuth } from "./RequireAuth";

function Protected({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <AppShell>{children}</AppShell>
    </RequireAuth>
  );
}

/** Milestone 10: isolamento reale anche lato route, non solo nel menu — un
 * link diretto a `/settings/integrations` con `GOOGLE_ENABLED=false` non
 * deve comunque raggiungere la pagina. */
function RequireGoogleEnabled({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!user?.google_enabled) return <Navigate to="/" replace />;
  return children;
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
      <Route path="/investments" element={<Protected><InvestmentsOverviewPage /></Protected>} />
      <Route path="/investments/portfolios/:portfolioId" element={<Protected><PortfolioDetailPage /></Protected>} />
      <Route path="/investments/assets/:assetId" element={<Protected><AssetDetailPage /></Protected>} />
      <Route path="/investments/tax" element={<Protected><TaxLossPocketPage /></Protected>} />
      <Route path="/investments/tax/realized-events" element={<Protected><TaxRealizedEventsPage /></Protected>} />
      <Route path="/accounts" element={<Protected><AccountsPage /></Protected>} />
      <Route path="/accounts/:accountId/edit" element={<Protected><AccountEditPage /></Protected>} />
      <Route path="/accounts/:accountId" element={<Protected><AccountDetailPage /></Protected>} />
      <Route path="/transactions" element={<Protected><TransactionsPage /></Protected>} />
      <Route path="/imports" element={<Protected><ImportsPage /></Protected>} />
      <Route path="/activity" element={<Protected><ActivityPage /></Protected>} />

      {/* Rework Navigation (SPEC_FE_REDESIGN §6-9): layout nidificato per
       * tutto il sottoalbero Settings — un solo Protected/AppShell invece di
       * ripeterlo su ognuna delle 8 route (com'era prima), hub come indice,
       * back-link automatico su ogni sotto-pagina via SettingsLayout. I path
       * delle 8 route restano invariati: nessun link esterno si rompe. */}
      <Route path="/settings" element={<Protected><Outlet /></Protected>}>
        <Route index element={<SettingsHubPage />} />
        <Route element={<SettingsLayout />}>
          <Route path="categories" element={<CategoriesSettingsPage />} />
          <Route path="rules" element={<RulesPage />} />
          <Route path="ai" element={<AISettingsPage />} />
          <Route path="market-data" element={<MarketDataSettingsPage />} />
          <Route path="currency" element={<CurrencySettingsPage />} />
          <Route path="tax" element={<TaxSettingsPage />} />
          <Route path="transaction-types" element={<TransactionTypeMappingsPage />} />
          <Route path="jobs" element={<JobsSettingsPage />} />
          <Route
            path="integrations"
            element={
              <RequireGoogleEnabled>
                <IntegrationsSettingsPage />
              </RequireGoogleEnabled>
            }
          />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
