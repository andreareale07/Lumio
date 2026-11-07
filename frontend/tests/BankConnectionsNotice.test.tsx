import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { BankConnectionsNotice } from "../src/features/settings/open-banking/BankConnectionsNotice";
import { SettingsHubPage } from "../src/features/settings/SettingsHubPage";

let mockUser: { open_banking_enabled?: boolean; google_enabled?: boolean } | null = null;
vi.mock("../src/app/providers/AuthProvider", () => ({ useAuth: () => ({ user: mockUser }) }));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderWithProviders(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const baseConnection = {
  id: "c1",
  aspsp_name: "Banca Test",
  aspsp_country: "IT",
  status: "active",
  valid_until: "2027-01-01T00:00:00Z",
  days_until_expiry: 100,
  expiring_soon: false,
  last_sync_at: null,
  last_error: null,
  sync_running: false,
  accounts: [],
};

describe("BankConnectionsNotice", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    mockUser = null;
  });

  it("con l'integrazione disattivata non fa nessuna richiesta e non mostra nulla", () => {
    mockUser = { open_banking_enabled: false };
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderWithProviders(<BankConnectionsNotice />);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("avvisa quando un'autorizzazione sta per scadere, con il link alla gestione", async () => {
    mockUser = { open_banking_enabled: true };
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse([{ ...baseConnection, expiring_soon: true, days_until_expiry: 4 }]),
    );
    renderWithProviders(<BankConnectionsNotice />);

    expect(await screen.findByText(/L'autorizzazione di Banca Test sta per scadere/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Gestisci" })).toHaveAttribute("href", "/settings/bank-connections");
  });

  it("segnala la sincronizzazione ferma quando e' scaduta", async () => {
    mockUser = { open_banking_enabled: true };
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse([{ ...baseConnection, status: "expired", days_until_expiry: -1 }]),
    );
    renderWithProviders(<BankConnectionsNotice />);
    expect(await screen.findByText(/è scaduta: la sincronizzazione è ferma/)).toBeInTheDocument();
  });

  it("non mostra nulla se tutte le autorizzazioni sono in regola", async () => {
    mockUser = { open_banking_enabled: true };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([baseConnection]));
    renderWithProviders(<BankConnectionsNotice />);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("Settings hub e Open Banking", () => {
  afterEach(() => {
    mockUser = null;
  });

  it("la voce compare solo quando l'integrazione e' attiva sull'istanza", () => {
    mockUser = { open_banking_enabled: false };
    const { unmount } = renderWithProviders(<SettingsHubPage />);
    expect(screen.queryByText("Conti bancari collegati")).not.toBeInTheDocument();
    unmount();

    mockUser = { open_banking_enabled: true };
    renderWithProviders(<SettingsHubPage />);
    expect(screen.getByText("Conti bancari collegati")).toBeInTheDocument();
  });
});
