import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SecuritySettingsPage } from "../src/features/settings/security/SecuritySettingsPage";

const refreshUser = vi.fn(async () => undefined);
let totpEnabled = false;

vi.mock("../src/app/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { totp_enabled: totpEnabled }, refreshUser }),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SecuritySettingsPage />
    </QueryClientProvider>,
  );
}

function stubApi(handlers: Record<string, () => Response>) {
  const fetchMock = vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    const key = Object.keys(handlers).find((path) => url.includes(path));
    return key ? handlers[key]() : new Response(null, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  totpEnabled = false;
  refreshUser.mockClear();
});

describe("SecuritySettingsPage", () => {
  it("attivazione: mostra la chiave, conferma col codice e aggiorna l'utente", async () => {
    const fetchMock = stubApi({
      "/auth/totp/setup": () =>
        new Response(JSON.stringify({ secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/Lumio:a?secret=JBSWY3DPEHPK3PXP" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      "/auth/totp/enable": () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Attiva" }));
    expect(await screen.findByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();

    const confirm = screen.getByRole("button", { name: "Conferma e attiva" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText("Codice a 6 cifre"), "123456");
    await user.click(confirm);

    await waitFor(() => expect(refreshUser).toHaveBeenCalled());
    const enableCall = fetchMock.mock.calls.find(([url]) => String(url).includes("/auth/totp/enable"));
    expect(JSON.parse(String(enableCall?.[1]?.body))).toEqual({ code: "123456" });
  });

  it("disattivazione: servono password e codice, con errore leggibile se rifiutata", async () => {
    totpEnabled = true;
    stubApi({ "/auth/totp/disable": () => new Response(JSON.stringify({ detail: "Invalid password" }), { status: 400 }) });
    const user = userEvent.setup();
    renderPage();

    const disable = screen.getByRole("button", { name: "Disattiva" });
    expect(disable).toBeDisabled();
    await user.type(screen.getByLabelText("Password"), "secret-pass-1");
    await user.type(screen.getByLabelText("Codice a 6 cifre"), "654321");
    await user.click(disable);

    expect(await screen.findByText("Password o codice non validi.")).toBeInTheDocument();
    expect(refreshUser).not.toHaveBeenCalled();
  });
});
