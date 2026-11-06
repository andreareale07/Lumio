import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { PeriodNavigator } from "../src/components/filters/PeriodNavigator";
import { periodForAnchor, shiftAnchor, type Granularity } from "../src/lib/period";

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

function renderNavigator(initialEntry: string, granularities?: Granularity[], allowAll?: boolean, family?: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <PeriodNavigator granularities={granularities} allowAll={allowAll} family={family} />
      <LocationDisplay />
    </MemoryRouter>,
  );
}

const search = () => screen.getByTestId("location").textContent ?? "";

beforeEach(() => sessionStorage.clear());

describe("PeriodNavigator", () => {
  it("naviga al periodo precedente preservando gli altri search params (es. tab= di AccountDetailPage)", async () => {
    const user = userEvent.setup();
    renderNavigator("/test?tab=analytics&account=acc-1&mode=granular&granularity=month&anchor=2026-03-01");

    await user.click(screen.getByRole("button", { name: "Periodo precedente" }));

    expect(search()).toContain("anchor=2026-02-01");
    expect(search()).toContain("tab=analytics");
    expect(search()).toContain("account=acc-1");
  });

  it("naviga al periodo successivo", async () => {
    const user = userEvent.setup();
    renderNavigator("/test?mode=granular&granularity=quarter&anchor=2026-01-01");

    await user.click(screen.getByRole("button", { name: "Periodo successivo" }));

    expect(search()).toContain("anchor=2026-04-01");
  });

  it("scrive in chiaro il periodo attivo con le date esatte", () => {
    renderNavigator("/test?mode=granular&granularity=month&anchor=2026-02-01");

    expect(screen.getByText("febbraio 2026")).toBeInTheDocument();
    expect(screen.getByText(/01 feb 2026 – 28 feb 2026/)).toBeInTheDocument();
  });

  describe("scelte a vista", () => {
    it("'Anno' porta all'anno corrente", async () => {
      const user = userEvent.setup();
      renderNavigator("/test?mode=granular&granularity=month&anchor=2020-01-01");

      await user.click(screen.getByRole("button", { name: "Anno" }));

      expect(search()).toContain("granularity=year");
      expect(search()).toContain(`anchor=${periodForAnchor("year", new Date()).date_from}`);
    });

    it("'Mese' dopo aver navigato torna al mese corrente", async () => {
      const user = userEvent.setup();
      renderNavigator("/test?mode=granular&granularity=month&anchor=2020-01-01");

      await user.click(screen.getByRole("button", { name: "Mese" }));

      expect(search()).toContain(`anchor=${periodForAnchor("month", new Date()).date_from}`);
    });

    it("'3M' e '12M' impostano una finestra mobile e disabilitano le frecce", async () => {
      const user = userEvent.setup();
      renderNavigator("/test?mode=granular&granularity=month&anchor=2026-03-01");

      await user.click(screen.getByRole("button", { name: "3M" }));

      expect(search()).toContain("mode=rolling");
      expect(search()).toContain("rolling=3m");
      expect(screen.getByText("Ultimi 3 mesi")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Periodo precedente" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Periodo successivo" })).toBeDisabled();

      await user.click(screen.getByRole("button", { name: "12M" }));
      expect(search()).toContain("rolling=12m");
    });

    it("il pulsante attivo e' marcato con aria-pressed", () => {
      renderNavigator("/test?mode=rolling&rolling=12m");

      expect(screen.getByRole("button", { name: "12M" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "3M" })).toHaveAttribute("aria-pressed", "false");
    });

    it("limita Mese/Anno a quelle consentite dalla pagina", () => {
      renderNavigator("/test", ["quarter"]);

      expect(screen.queryByRole("button", { name: "Mese" })).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Anno" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "3M" })).toBeInTheDocument();
    });
  });

  describe("pannello calendario", () => {
    it("applica un intervallo digitato (gg/mm/aaaa)", async () => {
      const user = userEvent.setup();
      renderNavigator("/test?mode=granular&granularity=month&anchor=2026-03-01");

      await user.click(screen.getByRole("button", { name: "Intervallo personalizzato" }));
      const dialog = screen.getByRole("dialog");
      await user.type(within(dialog).getByLabelText("Dal"), "01/01/2026");
      await user.tab();
      await user.type(within(dialog).getByLabelText("Al"), "31/01/2026");
      await user.tab();
      await user.click(within(dialog).getByRole("button", { name: "Applica" }));

      expect(search()).toContain("mode=custom");
      expect(search()).toContain("from=2026-01-01");
      expect(search()).toContain("to=2026-01-31");
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("applica un intervallo scelto con due tocchi sul calendario", async () => {
      const user = userEvent.setup();
      renderNavigator("/test?mode=custom&from=2026-01-10&to=2026-01-20");

      await user.click(screen.getByRole("button", { name: "Intervallo personalizzato" }));
      const dialog = screen.getByRole("dialog");
      // Il calendario si apre sul mese della data finale (gennaio 2026): due tocchi = nuovo intervallo.
      await user.click(within(dialog).getByRole("button", { name: /^05 gen 2026$/ }));
      await user.click(within(dialog).getByRole("button", { name: /^15 gen 2026$/ }));
      await user.click(within(dialog).getByRole("button", { name: "Applica" }));

      expect(search()).toContain("from=2026-01-05");
      expect(search()).toContain("to=2026-01-15");
    });

    it("segnala un formato non valido e una fine precedente all'inizio", async () => {
      const user = userEvent.setup();
      renderNavigator("/test");

      await user.click(screen.getByRole("button", { name: "Intervallo personalizzato" }));
      const dialog = screen.getByRole("dialog");
      await user.type(within(dialog).getByLabelText("Dal"), "2026-01-01");
      await user.tab();
      expect(within(dialog).getByRole("alert")).toHaveTextContent("Formato non valido");

      await user.clear(within(dialog).getByLabelText("Dal"));
      await user.type(within(dialog).getByLabelText("Dal"), "10/01/2026");
      await user.tab();
      await user.type(within(dialog).getByLabelText("Al"), "05/01/2026");
      await user.tab();
      expect(within(dialog).getByRole("alert")).toHaveTextContent("prima di quella iniziale");
      expect(within(dialog).getByRole("button", { name: "Applica" })).toBeDisabled();
    });

    it("rifiuta le date nel futuro", async () => {
      const user = userEvent.setup();
      renderNavigator("/test");

      await user.click(screen.getByRole("button", { name: "Intervallo personalizzato" }));
      const dialog = screen.getByRole("dialog");
      await user.type(within(dialog).getByLabelText("Al"), "01/01/2099");
      await user.tab();

      expect(within(dialog).getByRole("alert")).toHaveTextContent("nel futuro");
    });

    it("la scorciatoia del trimestre corrente e di quello scorso porta alla navigazione per trimestre", async () => {
      const user = userEvent.setup();
      renderNavigator("/test?mode=granular&granularity=month&anchor=2026-03-01");

      await user.click(screen.getByRole("button", { name: "Intervallo personalizzato" }));
      await user.click(screen.getByRole("button", { name: /· trimestre$/ }));
      expect(search()).toContain("granularity=quarter");
      expect(search()).toContain(`anchor=${periodForAnchor("quarter", new Date()).date_from}`);

      await user.click(screen.getByRole("button", { name: "Intervallo personalizzato" }));
      await user.click(screen.getByRole("button", { name: "Trimestre scorso" }));
      const previous = periodForAnchor("quarter", shiftAnchor("quarter", new Date(), -1)).date_from;
      expect(search()).toContain(`anchor=${previous}`);
    });

    it("senza il trimestre fra le granularita' consentite non offre le scorciatoie", async () => {
      const user = userEvent.setup();
      renderNavigator("/test", ["month", "year"]);

      await user.click(screen.getByRole("button", { name: "Intervallo personalizzato" }));

      expect(screen.queryByRole("button", { name: "Trimestre scorso" })).not.toBeInTheDocument();
    });

    it("si chiude con Annulla senza modificare l'URL", async () => {
      const user = userEvent.setup();
      renderNavigator("/test?mode=granular&granularity=month&anchor=2026-03-01");

      await user.click(screen.getByRole("button", { name: "Intervallo personalizzato" }));
      await user.click(screen.getByRole("button", { name: "Annulla" }));

      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(search()).toContain("anchor=2026-03-01");
    });
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

  it("un link con intervallo personalizzato (drill-down) mostra le date e disabilita le frecce", () => {
    renderNavigator("/test?mode=custom&from=2026-01-01&to=2026-01-31");

    expect(screen.getByRole("button", { name: "Periodo precedente" })).toBeDisabled();
    expect(screen.getAllByText(/01 gen 2026 – 31 gen 2026/).length).toBeGreaterThan(0);
  });

  describe("modalità 'Tutto' (allowAll)", () => {
    it("è il default quando allowAll è attivo e l'URL non ha ancora nessuno stato", () => {
      renderNavigator("/test", undefined, true);

      expect(screen.getByText("Tutti i periodi")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Tutto" })).toHaveAttribute("aria-pressed", "true");
      expect(search()).toBe("");
    });

    it("senza allowAll non c'è 'Tutto' e il default è il mese corrente", () => {
      renderNavigator("/test");

      expect(screen.queryByRole("button", { name: "Tutto" })).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Mese" })).toHaveAttribute("aria-pressed", "true");
    });

    it("'Mese' da 'Tutto' passa alla navigazione granulare", async () => {
      const user = userEvent.setup();
      renderNavigator("/test", undefined, true);

      await user.click(screen.getByRole("button", { name: "Mese" }));

      expect(search()).toContain("mode=granular");
    });

    it("'Tutto' da una vista granulare torna alla modalità senza filtro", async () => {
      const user = userEvent.setup();
      renderNavigator("/test?mode=granular&granularity=month&anchor=2026-03-01", undefined, true);

      await user.click(screen.getByRole("button", { name: "Tutto" }));

      expect(search()).toContain("mode=all");
      expect(screen.getByText("Tutti i periodi")).toBeInTheDocument();
    });
  });

  describe("famiglia di pagine", () => {
    it("ricorda l'ultimo periodo della famiglia e lo ripristina in una pagina senza stato", async () => {
      const first = renderNavigator("/analisi-a?mode=granular&granularity=year&anchor=2025-01-01", undefined, false, "analysis");
      await screen.findByText("2025");
      first.unmount();

      renderNavigator("/analisi-b", undefined, false, "analysis");

      expect(await screen.findByText((text) => text.includes("granularity=year"))).toBeInTheDocument();
      expect(search()).toContain("anchor=2025-01-01");
    });

    it("un link con periodo esplicito vince sul periodo ricordato", async () => {
      const first = renderNavigator("/a?mode=granular&granularity=year&anchor=2025-01-01", undefined, false, "analysis");
      await screen.findByText("2025");
      first.unmount();

      renderNavigator("/b?mode=granular&granularity=month&anchor=2026-02-01", undefined, false, "analysis");

      expect(screen.getByText("febbraio 2026")).toBeInTheDocument();
      expect(search()).toContain("granularity=month");
    });

    it("senza famiglia ogni pagina riparte dal proprio default", async () => {
      const first = renderNavigator("/a?mode=granular&granularity=year&anchor=2025-01-01");
      await screen.findByText("2025");
      first.unmount();

      renderNavigator("/b");

      expect(search()).toBe("");
      expect(screen.getByRole("button", { name: "Mese" })).toHaveAttribute("aria-pressed", "true");
    });
  });
});
