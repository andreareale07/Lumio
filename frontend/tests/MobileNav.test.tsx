import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { MobileNav } from "../src/components/layout/MobileNav";

function renderNav(initialPath = "/") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <MobileNav />
    </MemoryRouter>,
  );
}

describe("MobileNav", () => {
  it("da chiusa nasconde le altre voci e mostra 'Altro'", () => {
    renderNav();
    const more = screen.getByRole("button", { name: "Altro" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    // Le voci espanse sono aria-hidden: invisibili all'albero di accessibilita'.
    expect(screen.queryByRole("link", { name: "Spese" })).not.toBeInTheDocument();
  });

  it("'Altro' espande le altre voci e diventa 'Chiudi'", async () => {
    renderNav();
    await userEvent.click(screen.getByRole("button", { name: "Altro" }));

    const close = screen.getByRole("button", { name: "Chiudi" });
    expect(close).toHaveAttribute("aria-expanded", "true");
    for (const label of ["Spese", "Entrate", "Patrimonio", "Investimenti", "Attività", "Impostazioni"]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }

    await userEvent.click(close);
    expect(screen.getByRole("button", { name: "Altro" })).toBeInTheDocument();
  });

  it("scegliere una voce richiude la barra", async () => {
    renderNav();
    await userEvent.click(screen.getByRole("button", { name: "Altro" }));
    await userEvent.click(screen.getByRole("link", { name: "Spese" }));
    expect(screen.getByRole("button", { name: "Altro" })).toHaveAttribute("aria-expanded", "false");
  });

  it("Esc richiude la barra", async () => {
    renderNav();
    await userEvent.click(screen.getByRole("button", { name: "Altro" }));
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Altro" })).toBeInTheDocument();
  });
});
