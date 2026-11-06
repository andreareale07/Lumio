import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RangeSelector } from "../src/components/charts/RangeSelector";

describe("RangeSelector", () => {
  it("mostra tutti i preset e marca quello attivo con aria-pressed", () => {
    render(<RangeSelector value="3M" onChange={() => {}} />);

    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["1G", "1S", "1M", "3M", "6M", "1A", "5A", "Max"]);
    expect(screen.getByRole("button", { name: "3M" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "1M" })).toHaveAttribute("aria-pressed", "false");
  });

  it("notifica il preset scelto", async () => {
    const onChange = vi.fn();
    render(<RangeSelector value="3M" onChange={onChange} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "1A" }));

    expect(onChange).toHaveBeenCalledWith("1A");
  });

  it("e' solo testo: nessun bordo ne' sfondo sui pulsanti, area di tocco alta 40px", () => {
    render(<RangeSelector value="1M" onChange={() => {}} />);

    const button = screen.getByRole("button", { name: "3M" });
    expect(button.className).not.toMatch(/\bborder\b|\bbg-/);
    expect(button.className).toContain("h-10");
  });

  it("accetta un sottoinsieme di preset", () => {
    render(<RangeSelector value="1M" onChange={() => {}} presets={["1M", "1A", "Max"]} />);

    expect(screen.getAllByRole("button")).toHaveLength(3);
  });
});
