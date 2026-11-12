import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RuleBuilderDialog } from "../src/features/rules/RuleBuilderDialog";
import type { Category, RulePreview, Transaction } from "../src/types/api";

const CATEGORY: Category = {
  id: "cat-rata",
  workspace_id: null,
  parent_id: null,
  name: "Rata mutuo",
  code: "rata_mutuo",
  kind: "expense",
  is_system: false,
  is_active: true,
  sort_order: 10,
};

const TRANSACTION: Transaction = {
  id: "tx-1",
  workspace_id: "ws-1",
  financial_account_id: "acc-1",
  import_id: null,
  category_id: CATEGORY.id,
  transaction_date: "2026-11-05",
  value_date: null,
  description_raw: "BONIFICO SEPA ISTANTANEO TRN CCTX0012345 BENEF. Reale Francesco PER Rata Mutuo",
  description_normalized: null,
  merchant: null,
  counterparty_name: null,
  counterparty_iban: null,
  reference: null,
  amount: "-487.30",
  currency: "EUR",
  direction: "debit",
  transaction_type: "expense",
  balance_after: null,
  status: "confirmed",
  needs_review: false,
  created_at: "2026-11-05T00:00:00Z",
  updated_at: "2026-11-05T00:00:00Z",
};

const PREVIEW: RulePreview = {
  would_change: 3,
  already_correct: 8,
  protected: 1,
  recategorized: 1,
  other_category: 0,
  conflict_samples: [],
  total: 12,
  group: null,
  items: [],
  truncated: false,
};

interface Call {
  url: string;
  method: string;
  body: unknown;
}

function stubApi(overrides: { preview?: RulePreview; reclassifyStatus?: number } = {}) {
  const calls: Call[] = [];
  const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    const method = (init as RequestInit | undefined)?.method ?? "GET";
    const rawBody = (init as RequestInit | undefined)?.body;
    calls.push({ url, method, body: typeof rawBody === "string" ? JSON.parse(rawBody) : undefined });
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    if (url.includes("/categories")) return json([CATEGORY]);
    if (url.includes("/rules/preview")) return json(overrides.preview ?? PREVIEW);
    if (url.includes("/classification/reclassify")) {
      return overrides.reclassifyStatus === 409 ? json({ detail: "busy" }, 409) : json({ job_id: "job-1" }, 202);
    }
    if (url.endsWith("/rules") && method === "POST") return json({ id: "rule-1" }, 201);
    return json(null);
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

function renderBuilder(props: Partial<React.ComponentProps<typeof RuleBuilderDialog>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <RuleBuilderDialog open onClose={() => {}} transaction={TRANSACTION} {...props} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RuleBuilderDialog", () => {
  it("dal movimento mostra le parole, segna i numeri come variabili e parte dalla causale", async () => {
    stubApi();
    renderBuilder();

    const picker = await screen.findByRole("region", { name: "Dal movimento" });
    expect(within(picker).getByRole("button", { name: "Rata" })).toHaveAttribute("aria-pressed", "true");
    expect(within(picker).getByRole("button", { name: "BONIFICO" })).toHaveAttribute("aria-pressed", "false");
    // Una parola con cifre non è un pulsante: cambia a ogni movimento.
    expect(within(picker).queryByRole("button", { name: "CCTX0012345" })).not.toBeInTheDocument();
    expect(screen.getByText("CCTX0012345")).toBeInTheDocument();
  });

  it("la frase della regola segue le parole scelte", async () => {
    stubApi();
    const user = userEvent.setup();
    renderBuilder();
    const picker = await screen.findByRole("region", { name: "Dal movimento" });

    await user.click(within(picker).getByRole("button", { name: "Deseleziona" }));
    expect(await screen.findAllByText("Scegli almeno una parte del movimento.")).not.toHaveLength(0);

    await user.click(within(picker).getByRole("button", { name: "Rata" }));
    await user.click(within(picker).getByRole("button", { name: "Mutuo" }));
    expect(await screen.findByText("«Rata Mutuo»")).toBeInTheDocument();
  });

  it("non avvisa quando i movimenti che cambiano sono solo senza categoria", async () => {
    stubApi({ preview: { ...PREVIEW, would_change: 15, recategorized: 0, already_correct: 2, total: 18 } });
    renderBuilder();

    await screen.findByTestId("impact-counters");
    expect(screen.queryByText(/Toglierebbe da altre categorie/)).not.toBeInTheDocument();
  });

  it("mostra quanti movimenti cambiano, sono già giusti e sono protetti", async () => {
    stubApi();
    renderBuilder();

    const counters = await screen.findByTestId("impact-counters");
    expect(within(counters).getByText("3")).toBeInTheDocument();
    expect(within(counters).getByText("8")).toBeInTheDocument();
    expect(within(counters).getByText("1")).toBeInTheDocument();
    expect(screen.getByText("Vedi i 12 movimenti")).toBeInTheDocument();
  });

  it("avvisa quando la regola cambierebbe più categorie di quelle già giuste", async () => {
    stubApi({ preview: { ...PREVIEW, would_change: 15, recategorized: 15, already_correct: 8, total: 24 } });
    renderBuilder();

    expect(await screen.findByText(/Toglierebbe da altre categorie 15 movimenti/)).toBeInTheDocument();
  });

  it("segnala il conflitto con un'altra categoria e propone di escludere la parola che distingue", async () => {
    const calls = stubApi({
      preview: {
        ...PREVIEW,
        would_change: 0,
        recategorized: 0,
        protected: 1,
        other_category: 1,
        conflict_samples: ["CASHBACK SCONTI BENEF. Reale Francesco PER Rata Mutuo"],
      },
    });
    const user = userEvent.setup();
    renderBuilder();

    expect(await screen.findByText(/Prenderebbe anche 1 movimento che ha già un'altra categoria/)).toBeInTheDocument();
    expect(screen.getByText(/CASHBACK SCONTI BENEF/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Escludi «CASHBACK»" }));
    expect(await screen.findByText("«CASHBACK»")).toBeInTheDocument();
    // Una volta esclusa, la proposta non si ripete.
    expect(screen.queryByRole("button", { name: "Escludi «CASHBACK»" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Crea regola" }));
    const created = await waitFor(() => {
      const call = calls.find((c) => c.url.endsWith("/rules") && c.method === "POST");
      expect(call).toBeTruthy();
      return call;
    });
    expect(created?.body).toMatchObject({
      conditions: [
        { field: "description", operator: "contains" },
        { field: "description", operator: "not_contains", value: "CASHBACK" },
      ],
      match_mode: "all",
    });
  });

  it("se non si può salvare lo dice accanto al pulsante invece di non fare nulla", async () => {
    const calls = stubApi();
    const user = userEvent.setup();
    renderBuilder();
    const picker = await screen.findByRole("region", { name: "Dal movimento" });
    await user.click(within(picker).getByRole("button", { name: "Deseleziona" }));

    await user.click(screen.getByRole("button", { name: "Crea regola" }));

    // Una volta nella sezione delle condizioni e una accanto al pulsante.
    expect(await screen.findAllByText("Aggiungi almeno una condizione")).toHaveLength(2);
    expect(calls.some((c) => c.url.endsWith("/rules") && c.method === "POST")).toBe(false);
  });

  it("crea la regola con le condizioni scelte e la applica ai movimenti esistenti", async () => {
    const calls = stubApi();
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderBuilder({ onClose });
    await screen.findByTestId("impact-counters");
    expect(screen.getByRole("checkbox", { name: /Applica anche ai 3 movimenti esistenti/ })).toBeChecked();

    await user.click(screen.getByRole("button", { name: "Crea regola" }));

    await waitFor(() => expect(calls.some((c) => c.url.includes("/classification/reclassify"))).toBe(true));
    const created = calls.find((c) => c.url.endsWith("/rules") && c.method === "POST");
    expect(created?.body).toMatchObject({
      conditions: [{ field: "description", operator: "contains", value: "BENEF. Reale Francesco PER Rata Mutuo" }],
      match_mode: "all",
      category_id: CATEGORY.id,
      name: "BENEF. Reale Francesco PER Rata Mutuo",
    });
    const applied = calls.find((c) => c.url.includes("/classification/reclassify"));
    expect(applied?.body).toEqual({ scope: "all_except_manual", run_ai: false, rule_id: "rule-1" });
    expect(await screen.findByText(/L'aggiornamento dei movimenti è in corso/)).toBeInTheDocument();
  });

  it("senza la spunta non lancia l'aggiornamento e conferma la creazione", async () => {
    const calls = stubApi();
    const user = userEvent.setup();
    renderBuilder();
    await screen.findByTestId("impact-counters");

    await user.click(screen.getByRole("checkbox", { name: /Applica anche/ }));
    await user.click(screen.getByRole("button", { name: "Crea regola" }));

    expect(await screen.findByText(/Vale per i movimenti che arriveranno/)).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes("/classification/reclassify"))).toBe(false);
  });

  it("se nessun movimento cambia non chiude in silenzio: conferma e si chiude col pulsante", async () => {
    stubApi({ preview: { ...PREVIEW, would_change: 0, protected: 2, already_correct: 1, total: 3 } });
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderBuilder({ onClose });
    await screen.findByTestId("impact-counters");

    await user.click(screen.getByRole("button", { name: "Crea regola" }));

    expect(await screen.findByText(/Regola creata\. Vale per i movimenti che arriveranno/)).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getAllByRole("button", { name: "Chiudi" }).at(-1)!);
    expect(onClose).toHaveBeenCalled();
  });

  it("se un'altra riclassificazione è in corso lo dice senza perdere la regola creata", async () => {
    stubApi({ reclassifyStatus: 409 });
    const user = userEvent.setup();
    renderBuilder();
    await screen.findByTestId("impact-counters");

    await user.click(screen.getByRole("button", { name: "Crea regola" }));

    expect(await screen.findByText(/Un'altra riclassificazione è in corso/)).toBeInTheDocument();
  });

  it("Personalizza permette di aggiungere una condizione sull'importo", async () => {
    const calls = stubApi();
    const user = userEvent.setup();
    renderBuilder();
    await screen.findByTestId("impact-counters");

    await user.click(screen.getByRole("button", { name: "Personalizza" }));
    await user.click(screen.getByRole("button", { name: "Aggiungi condizione sull'importo" }));
    await user.type(screen.getByLabelText("Importo minimo (€)"), "450");
    await user.type(screen.getByLabelText("Importo massimo (€)"), "520");

    await waitFor(() => {
      const withAmount = calls.filter(
        (c) =>
          c.url.includes("/rules/preview") &&
          JSON.stringify(c.body).includes('"field":"amount"') &&
          JSON.stringify(c.body).includes('"max":"520"'),
      );
      expect(withAmount.length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText(/l'importo è tra 450 e 520 €/).length).toBeGreaterThan(0);
    expect(screen.getByText("tutte")).toBeInTheDocument();
  });

  it("senza movimento di partenza chiede un testo e rifiuta una regex non valida", async () => {
    stubApi();
    const user = userEvent.setup();
    renderBuilder({ transaction: null });

    expect(screen.queryByRole("region", { name: "Dal movimento" })).not.toBeInTheDocument();
    const operator = await screen.findByLabelText("Confronto");
    await user.selectOptions(operator, "regex");
    const value = screen.getByLabelText("Testo");
    await user.click(value);
    await user.paste("[abc");
    await user.click(screen.getByRole("button", { name: "Crea regola" }));

    expect(await screen.findByText("Espressione regolare non valida")).toBeInTheDocument();
  });
});
