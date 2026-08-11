import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "../src/App";

describe("App", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("un utente non autenticato viene reindirizzato al login", async () => {
    // Nessuna sessione valida: /auth/refresh (chiamato al mount da
    // AuthProvider) risponde 401, quindi RequireAuth reindirizza a /login.
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 401 }));

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Lumio" })).toBeInTheDocument();
    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  });
});
