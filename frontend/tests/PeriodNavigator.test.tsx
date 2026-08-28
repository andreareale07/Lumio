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

  it("cambiare granularità dal menu ricalcola l'ancora sul bucket corrispondente", async () => {
    const user = userEvent.setup();
    renderNavigator("/test?mode=granular&granularity=month&anchor=2026-02-01");

    await user.click(screen.getByRole("button", { name: "febbraio 2026" }));
    await user.click(screen.getByRole("menuitemradio", { name: "Trimestre" }));

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

  it("apre il pannello dell'intervallo personalizzato e lo applica", async () => {
    const user = userEvent.setup();
    renderNavigator("/test?mode=granular&granularity=month&anchor=2026-03-01");

    await user.click(screen.getByRole("button", { name: "Intervallo personalizzato" }));
    expect(screen.getByLabelText("Dal")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Dal"), "2026-01-01");
    await user.type(screen.getByLabelText("Al"), "2026-01-31");
    await user.click(screen.getByRole("button", { name: "Applica" }));

    const search = screen.getByTestId("location").textContent;
    expect(search).toContain("mode=custom");
    expect(search).toContain("from=2026-01-01");
    expect(search).toContain("to=2026-01-31");
  });

  it("limita le opzioni di granularità a quelle passate dalla pagina", async () => {
    const user = userEvent.setup();
    renderNavigator("/test?mode=granular&granularity=month&anchor=2026-03-01", ["month", "quarter", "year"]);

    await user.click(screen.getByRole("button", { name: "marzo 2026" }));

    const options = screen.getAllByRole("menuitemradio").map((o) => o.textContent);
    expect(options).toEqual(["Mese", "Trimestre", "Anno"]);
  });

  describe("modalità 'Max' (allowAll)", () => {
    it("è il default quando allowAll è attivo e l'URL non ha ancora nessuno stato", () => {
      renderNavigator("/test", undefined, true);

      expect(screen.getByText("Max")).toBeInTheDocument();
      expect(screen.getByTestId("location").textContent).toBe("");
    });

    it("senza allowAll il default resta granulare (mese corrente), non 'Max'", () => {
      renderNavigator("/test");

      expect(screen.queryByText("Max")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Periodo successivo" })).toBeInTheDocument();
    });

    it("selezionare una granularità dal menu in modalità 'Max' passa alla navigazione granulare", async () => {
      const user = userEvent.setup();
      renderNavigator("/test", undefined, true);

      await user.click(screen.getByRole("button", { name: "Max" }));
      await user.click(screen.getByRole("menuitemradio", { name: "Mese" }));

      expect(screen.getByTestId("location").textContent).toContain("mode=granular");
    });

    it("'Max' dal menu in vista granulare torna alla modalità senza filtro", async () => {
      const user = userEvent.setup();
      renderNavigator("/test?mode=granular&granularity=month&anchor=2026-03-01", undefined, true);

      await user.click(screen.getByRole("button", { name: "marzo 2026" }));
      await user.click(screen.getByRole("menuitemradio", { name: "Max" }));

      expect(screen.getByTestId("location").textContent).toContain("mode=all");
      expect(screen.getByText("Max")).toBeInTheDocument();
    });
  });
});
