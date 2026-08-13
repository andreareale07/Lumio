import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { PeriodNavigator } from "../src/components/filters/PeriodNavigator";
import { periodForAnchor, type Granularity } from "../src/lib/period";

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

function renderNavigator(initialEntry: string, granularities?: Granularity[], allowAll?: boolean) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <PeriodNavigator granularities={granularities} allowAll={allowAll} />
      <LocationDisplay />
    </MemoryRouter>,
  );
}

describe("PeriodNavigator", () => {
  it("naviga al periodo precedente preservando gli altri search params (es. tab= di AccountDetailPage)", async () => {
    const user = userEvent.setup();
    renderNavigator("/test?tab=analytics&account=acc-1&mode=granular&granularity=month&anchor=2026-03-01");

    await user.click(screen.getByRole("button", { name: "Periodo precedente" }));

    const search = screen.getByTestId("location").textContent;
    expect(search).toContain("anchor=2026-02-01");
    expect(search).toContain("tab=analytics");
    expect(search).toContain("account=acc-1");
  });

  it("naviga al periodo successivo", async () => {
    const user = userEvent.setup();
    renderNavigator("/test?mode=granular&granularity=quarter&anchor=2026-01-01");

    await user.click(screen.getByRole("button", { name: "Periodo successivo" }));

    expect(screen.getByTestId("location").textContent).toContain("anchor=2026-04-01");
  });

  it("cambiare granularità ricalcola l'ancora sul bucket corrispondente", async () => {
    const user = userEvent.setup();
    renderNavigator("/test?mode=granular&granularity=month&anchor=2026-02-01");

    await user.selectOptions(screen.getByLabelText("Granularità"), "quarter");

    const search = screen.getByTestId("location").textContent;
    expect(search).toContain("anchor=2026-01-01");
    expect(search).toContain("granularity=quarter");
  });

  it("il bottone 'Oggi' porta al bucket che contiene la data reale", async () => {
    const user = userEvent.setup();
    renderNavigator("/test?mode=granular&granularity=month&anchor=2020-01-01");

    await user.click(screen.getByRole("button", { name: "Oggi" }));

    const expectedAnchor = periodForAnchor("month", new Date()).date_from;
    expect(screen.getByTestId("location").textContent).toContain(`anchor=${expectedAnchor}`);
  });

  it("migra un vecchio ?period=this_month al nuovo modello granulare", async () => {
    renderNavigator("/test?period=this_month");

    const expectedAnchor = periodForAnchor("month", new Date()).date_from;
    expect(await screen.findByText((text) => text.includes(`anchor=${expectedAnchor}`))).toBeInTheDocument();
  });

  it("migra un vecchio ?period=last_3_months a un range personalizzato congelato", async () => {
    renderNavigator("/test?period=last_3_months");

    expect(await screen.findByText((text) => text.includes("mode=custom"))).toBeInTheDocument();
  });

  it("passa a intervallo personalizzato e torna alla navigazione per periodo", async () => {
    const user = userEvent.setup();
    renderNavigator("/test?mode=granular&granularity=month&anchor=2026-03-01");

    await user.click(screen.getByRole("button", { name: "Intervallo personalizzato" }));
    expect(screen.getByLabelText("Dal")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Torna alla navigazione per periodo" }));
    expect(screen.getByLabelText("Granularità")).toBeInTheDocument();
  });

  it("limita le opzioni di granularità a quelle passate dalla pagina", () => {
    renderNavigator("/test?mode=granular&granularity=month&anchor=2026-03-01", ["month", "quarter", "year"]);

    const select = screen.getByLabelText("Granularità") as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(["month", "quarter", "year"]);
  });

  describe("modalità 'Tutti i periodi' (allowAll)", () => {
    it("è il default quando allowAll è attivo e l'URL non ha ancora nessuno stato", () => {
      renderNavigator("/test", undefined, true);

      expect(screen.getByText("Tutti i periodi")).toBeInTheDocument();
      expect(screen.getByTestId("location").textContent).toBe("");
    });

    it("senza allowAll il default resta granulare (mese corrente), non 'tutti i periodi'", () => {
      renderNavigator("/test");

      expect(screen.queryByText("Tutti i periodi")).not.toBeInTheDocument();
      expect(screen.getByLabelText("Granularità")).toBeInTheDocument();
    });

    it("'Filtra per periodo' passa alla navigazione granulare", async () => {
      const user = userEvent.setup();
      renderNavigator("/test", undefined, true);

      await user.click(screen.getByRole("button", { name: "Filtra per periodo" }));

      expect(screen.getByTestId("location").textContent).toContain("mode=granular");
      expect(screen.getByLabelText("Granularità")).toBeInTheDocument();
    });

    it("'Tutti i periodi' dalla vista granulare torna alla modalità senza filtro", async () => {
      const user = userEvent.setup();
      renderNavigator("/test?mode=granular&granularity=month&anchor=2026-03-01", undefined, true);

      await user.click(screen.getByRole("button", { name: "Tutti i periodi" }));

      expect(screen.getByTestId("location").textContent).toContain("mode=all");
      expect(screen.getByText("Tutti i periodi")).toBeInTheDocument();
    });
  });
});
