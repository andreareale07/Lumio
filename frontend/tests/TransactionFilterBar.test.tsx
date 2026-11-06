import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setDesktop } from "./matchMedia";

import { TransactionFilterBar, type SelectFilter } from "../src/features/transactions/TransactionFilterBar";

const baseFilters: SelectFilter[] = [
  { key: "account", label: "Conto", values: [], options: [{ value: "a1", label: "Conto verifica" }] },
  {
    key: "category",
    label: "Categoria",
    values: [],
    options: [
      { value: "c1", label: "Alimentari › Supermercato" },
      { value: "c2", label: "Casa › Affitto" },
      ...["Mutuo", "Utenze", "Trasporti", "Salute", "Svago", "Viaggi"].map((name, i) => ({
        value: `x${i}`,
        label: `Altro › ${name}`,
      })),
    ],
  },
];

function renderBar(overrides: Partial<React.ComponentProps<typeof TransactionFilterBar>> = {}) {
  const props: React.ComponentProps<typeof TransactionFilterBar> = {
    searchText: "",
    onSearchTextChange: vi.fn(),
    selectFilters: baseFilters,
    onSetFilterValues: vi.fn(),
    staticChips: [],
    review: null,
    hasAnyFilter: false,
    onClearAll: vi.fn(),
    summary: undefined,
    ...overrides,
  };
  render(<TransactionFilterBar {...props} />);
  return props;
}

describe("TransactionFilterBar (desktop: popover, applicazione immediata)", () => {
  beforeEach(() => setDesktop(true));
  afterEach(() => setDesktop(false));

  it("'+ Filtro' propone i filtri non ancora attivi e applica il valore scelto", async () => {
    const props = renderBar();
    await userEvent.click(screen.getByRole("button", { name: /Filtro/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Categoria" }));
    await userEvent.type(screen.getByRole("searchbox", { name: /Cerca categoria/ }), "affitto");
    expect(screen.queryByText("Alimentari › Supermercato")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Casa › Affitto" }));
    expect(props.onSetFilterValues).toHaveBeenCalledWith("category", ["c2"]);
  });

  it("mostra un chip per il filtro attivo e lo rimuove con la X", async () => {
    const props = renderBar({
      selectFilters: [{ ...baseFilters[0]!, values: ["a1"] }, baseFilters[1]!],
      hasAnyFilter: true,
    });
    expect(screen.getByRole("button", { name: /^Conto:/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Rimuovi il filtro Conto/ }));
    expect(props.onSetFilterValues).toHaveBeenCalledWith("account", []);
  });

  it("con piu' valori il chip mostra il primo e '+N', e il picker aggiunge senza sostituire", async () => {
    const props = renderBar({
      selectFilters: [baseFilters[0]!, { ...baseFilters[1]!, values: ["c1"] }],
      hasAnyFilter: true,
    });
    await userEvent.click(screen.getByRole("button", { name: /^Categoria:/ }));
    await userEvent.click(screen.getByRole("button", { name: /Casa › Affitto/ }));
    expect(props.onSetFilterValues).toHaveBeenCalledWith("category", ["c1", "c2"]);
  });

  it("il chip riassume una selezione multipla", () => {
    renderBar({
      selectFilters: [baseFilters[0]!, { ...baseFilters[1]!, values: ["c1", "c2"] }],
      hasAnyFilter: true,
    });
    expect(screen.getByRole("button", { name: /^Categoria:.*\+1/ })).toBeInTheDocument();
  });

  it("'Azzera filtri' compare solo con filtri attivi", async () => {
    renderBar();
    expect(screen.queryByRole("button", { name: "Azzera filtri" })).not.toBeInTheDocument();
  });

  it("mostra il riepilogo con conteggio, entrate e uscite", () => {
    renderBar({
      summary: { count: 4, currency: "EUR", income: "0.00", expenses: "482.00", net: "-482.00" },
    });
    expect(screen.getByText(/4 movimenti/)).toBeInTheDocument();
    expect(screen.getByText(/uscite/)).toBeInTheDocument();
  });
});

describe("TransactionFilterBar (smartphone: bottom sheet con Applica)", () => {
  beforeEach(() => setDesktop(false));

  it("le scelte si applicano solo con 'Applica', non a ogni tocco", async () => {
    const props = renderBar();
    await userEvent.click(screen.getByRole("button", { name: /Filtro/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Categoria" }));
    expect(screen.getByRole("dialog", { name: "Categoria" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Casa › Affitto" }));
    await userEvent.click(screen.getByRole("button", { name: "Alimentari › Supermercato" }));
    expect(props.onSetFilterValues).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /^Applica · 2$/ }));
    expect(props.onSetFilterValues).toHaveBeenCalledWith("category", ["c2", "c1"]);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("chiudere senza applicare scarta la bozza", async () => {
    const props = renderBar();
    await userEvent.click(screen.getByRole("button", { name: /Filtro/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Conto" }));
    await userEvent.click(screen.getByRole("button", { name: "Conto verifica" }));
    await userEvent.click(screen.getByRole("button", { name: "Chiudi" }));

    expect(props.onSetFilterValues).not.toHaveBeenCalled();
  });

  it("il campo di ricerca del picker non prende il focus da solo (niente tastiera a sorpresa)", async () => {
    renderBar();
    await userEvent.click(screen.getByRole("button", { name: /Filtro/ }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Categoria" }));

    expect(screen.getByRole("searchbox", { name: /Cerca categoria/ })).not.toHaveFocus();
  });

  it("'Azzera' svuota la bozza e 'Applica' toglie il filtro", async () => {
    const props = renderBar({
      selectFilters: [baseFilters[0]!, { ...baseFilters[1]!, values: ["c1"] }],
      hasAnyFilter: true,
    });
    await userEvent.click(screen.getByRole("button", { name: /^Categoria:/ }));
    await userEvent.click(screen.getByRole("button", { name: "Azzera" }));
    await userEvent.click(screen.getByRole("button", { name: "Applica" }));

    expect(props.onSetFilterValues).toHaveBeenCalledWith("category", []);
  });
});
