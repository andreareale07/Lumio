import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { useRangeParam } from "../src/lib/useRangeParam";

const PRESETS = ["1M", "3M", "1A"] as const;

function Probe() {
  const [range, setRange] = useRangeParam("investments", PRESETS, "3M");
  const location = useLocation();
  return (
    <div>
      <span data-testid="range">{range}</span>
      <span data-testid="search">{location.search}</span>
      <button onClick={() => setRange("1A")}>scegli 1A</button>
    </div>
  );
}

const renderProbe = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Probe />
    </MemoryRouter>,
  );

beforeEach(() => sessionStorage.clear());

describe("useRangeParam", () => {
  it("senza URL ne' memoria usa il default della pagina", () => {
    renderProbe("/a");
    expect(screen.getByTestId("range")).toHaveTextContent("3M");
  });

  it("legge l'intervallo dall'URL e ignora i valori non validi", () => {
    renderProbe("/a?range=1M");
    expect(screen.getByTestId("range")).toHaveTextContent("1M");
  });

  it("un valore non valido nell'URL ricade sul default", () => {
    renderProbe("/a?range=9X");
    expect(screen.getByTestId("range")).toHaveTextContent("3M");
  });

  it("scegliere un intervallo lo scrive nell'URL preservando gli altri parametri", async () => {
    renderProbe("/a?tab=x");
    await userEvent.setup().click(screen.getByText("scegli 1A"));

    expect(screen.getByTestId("search")).toHaveTextContent("tab=x");
    expect(screen.getByTestId("search")).toHaveTextContent("range=1A");
    expect(screen.getByTestId("range")).toHaveTextContent("1A");
  });

  it("ricorda l'ultimo intervallo della famiglia in un'altra pagina senza parametro", async () => {
    const first = renderProbe("/a");
    await userEvent.setup().click(screen.getByText("scegli 1A"));
    first.unmount();

    renderProbe("/b");
    expect(screen.getByTestId("range")).toHaveTextContent("1A");
  });
});
