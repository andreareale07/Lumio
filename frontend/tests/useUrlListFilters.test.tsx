import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { useUrlListFilters } from "../src/lib/useUrlListFilters";

function Probe() {
  const { query, setQuery, getValues, setValues, clearAll, hasAnyFilter } = useUrlListFilters(["status"]);
  const location = useLocation();
  return (
    <div>
      <span data-testid="q">{query}</span>
      <span data-testid="status">{getValues("status").join(",")}</span>
      <span data-testid="any">{String(hasAnyFilter)}</span>
      <span data-testid="search">{location.search}</span>
      <button onClick={() => setQuery("netflix")}>cerca</button>
      <button onClick={() => setValues("status", ["active", "inactive"])}>stati</button>
      <button onClick={() => clearAll()}>azzera</button>
    </div>
  );
}

const renderProbe = (entry = "/x") =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Probe />
    </MemoryRouter>,
  );

describe("useUrlListFilters", () => {
  it("legge ricerca e valori dall'URL", () => {
    renderProbe("/x?q=abc&status=active&status=inactive");
    expect(screen.getByTestId("q")).toHaveTextContent("abc");
    expect(screen.getByTestId("status")).toHaveTextContent("active,inactive");
    expect(screen.getByTestId("any")).toHaveTextContent("true");
  });

  it("scrive ricerca e valori ripetuti preservando gli altri parametri", async () => {
    renderProbe("/x?tab=1");
    const user = userEvent.setup();
    await user.click(screen.getByText("cerca"));
    await user.click(screen.getByText("stati"));

    const search = screen.getByTestId("search").textContent ?? "";
    expect(search).toContain("tab=1");
    expect(search).toContain("q=netflix");
    expect(search).toContain("status=active&status=inactive");
  });

  it("'azzera' toglie ricerca e filtri ma non gli altri parametri", async () => {
    renderProbe("/x?tab=1&q=abc&status=active");
    await userEvent.setup().click(screen.getByText("azzera"));

    expect(screen.getByTestId("search")).toHaveTextContent("?tab=1");
    expect(screen.getByTestId("any")).toHaveTextContent("false");
  });
});
