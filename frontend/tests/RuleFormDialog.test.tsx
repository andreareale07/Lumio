import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RuleFormDialog } from "../src/features/rules/RuleFormDialog";
import type { Category } from "../src/types/api";

const CATEGORIES: Category[] = [
  { id: "streaming", workspace_id: null, parent_id: null, name: "Streaming", code: "streaming", is_system: true, is_active: true, sort_order: 10 },
];

function renderDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RuleFormDialog open onClose={() => {}} />
    </QueryClientProvider>,
  );
}

function mockFetchSequence(...responses: Response[]) {
  const fetchMock = vi.spyOn(globalThis, "fetch");
  responses.forEach((response) => fetchMock.mockResolvedValueOnce(response));
  return fetchMock;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

describe("RuleFormDialog", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("rifiuta merchant_equals quando il campo non è 'merchant'", async () => {
    mockFetchSequence(jsonResponse(CATEGORIES));
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(screen.getByRole("option", { name: "Streaming" })).toBeInTheDocument());

    await user.type(screen.getByLabelText("Nome"), "Netflix");
    await user.selectOptions(screen.getByLabelText("Operatore"), "merchant_equals");
    await user.type(screen.getByLabelText("Valore"), "Netflix");
    await user.selectOptions(screen.getByLabelText("Categoria"), "streaming");
    await user.click(screen.getByRole("button", { name: "Crea regola" }));

    expect(await screen.findByText("'merchant_equals' richiede il campo Merchant")).toBeInTheDocument();
  });

  it("rifiuta una regex non valida", async () => {
    mockFetchSequence(jsonResponse(CATEGORIES));
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(screen.getByRole("option", { name: "Streaming" })).toBeInTheDocument());

    await user.type(screen.getByLabelText("Nome"), "Netflix");
    await user.selectOptions(screen.getByLabelText("Operatore"), "regex");
    // userEvent.type interpreta [ e ] come modificatori di tasti speciali:
    // per un valore letterale con parentesi quadre serve fireEvent.change.
    fireEvent.change(screen.getByLabelText("Valore"), { target: { value: "[unterminated" } });
    await user.selectOptions(screen.getByLabelText("Categoria"), "streaming");
    await user.click(screen.getByRole("button", { name: "Crea regola" }));

    expect(await screen.findByText("Espressione regolare non valida")).toBeInTheDocument();
  });

  it("invia la regola quando i dati sono validi", async () => {
    const fetchMock = mockFetchSequence(
      jsonResponse(CATEGORIES),
      jsonResponse({ id: "r1", workspace_id: "w1", name: "Netflix", field: "description", operator: "contains", value: "netflix", category_id: "streaming", priority: 100, is_active: true, created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:00:00Z" }, 201),
    );
    const user = userEvent.setup();
    renderDialog();

    await waitFor(() => expect(screen.getByRole("option", { name: "Streaming" })).toBeInTheDocument());

    await user.type(screen.getByLabelText("Nome"), "Netflix");
    await user.type(screen.getByLabelText("Valore"), "netflix");
    await user.selectOptions(screen.getByLabelText("Categoria"), "streaming");
    await user.click(screen.getByRole("button", { name: "Crea regola" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [, options] = fetchMock.mock.calls[1];
    const body = JSON.parse(options?.body as string);
    expect(body).toMatchObject({ name: "Netflix", field: "description", operator: "contains", value: "netflix", category_id: "streaming" });
  });
});
