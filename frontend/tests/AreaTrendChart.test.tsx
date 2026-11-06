import { fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AreaTrendChart, type TrendPoint } from "../src/components/charts/AreaTrendChart";

const DATA: TrendPoint[] = Array.from({ length: 11 }, (_, i) => ({ period: `2026-01-${i + 1}`, label: `${i + 1} gen`, value: 100 + i }));

function mockRect() {
  // Larghezza 464 = asse Y (64) + area di tracciamento (392) + margine destro (8).
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    left: 0, right: 464, top: 0, bottom: 200, width: 464, height: 200, x: 0, y: 0, toJSON: () => ({}),
  });
}

// jsdom non ha PointerEvent: un MouseEvent con il nome dell'evento puntatore
// porta comunque `clientX`, che e' quanto legge il gestore.
function pointer(el: HTMLElement, type: string, clientX = 0) {
  fireEvent(el, new MouseEvent(type, { bubbles: true, clientX }));
}

describe("AreaTrendChart esplorabile", () => {
  afterEach(() => vi.restoreAllMocks());

  it("ricava l'indice del punto dalla posizione del puntatore e lo notifica", () => {
    mockRect();
    const onActivePointChange = vi.fn();
    const { container } = render(
      <AreaTrendChart data={DATA} currency="EUR" onActivePointChange={onActivePointChange} />,
    );
    const wrapper = container.firstElementChild as HTMLElement;

    pointer(wrapper, "pointermove", 64);
    expect(onActivePointChange).toHaveBeenLastCalledWith(0);

    pointer(wrapper, "pointermove", 64 + 196);
    expect(onActivePointChange).toHaveBeenLastCalledWith(5);

    pointer(wrapper, "pointermove", 460);
    expect(onActivePointChange).toHaveBeenLastCalledWith(10);
  });

  it("limita l'indice ai bordi (dito sopra l'asse o oltre il margine)", () => {
    mockRect();
    const onActivePointChange = vi.fn();
    const { container } = render(<AreaTrendChart data={DATA} currency="EUR" onActivePointChange={onActivePointChange} />);
    const wrapper = container.firstElementChild as HTMLElement;

    pointer(wrapper, "pointerdown", 0);
    expect(onActivePointChange).toHaveBeenLastCalledWith(0);
    pointer(wrapper, "pointerdown", 9999);
    expect(onActivePointChange).toHaveBeenLastCalledWith(10);
  });

  it("notifica null quando il dito si solleva o esce dal grafico", () => {
    mockRect();
    const onActivePointChange = vi.fn();
    const { container } = render(<AreaTrendChart data={DATA} currency="EUR" onActivePointChange={onActivePointChange} />);
    const wrapper = container.firstElementChild as HTMLElement;

    pointer(wrapper, "pointermove", 200);
    pointer(wrapper, "pointerup");
    expect(onActivePointChange).toHaveBeenLastCalledWith(null);

    pointer(wrapper, "pointermove", 200);
    pointer(wrapper, "pointerout");
    expect(onActivePointChange).toHaveBeenLastCalledWith(null);
  });

  it("senza callback il grafico non e' esplorabile (nessun gestore di puntatore)", () => {
    mockRect();
    const { container } = render(<AreaTrendChart data={DATA} currency="EUR" />);

    expect((container.firstElementChild as HTMLElement).className).not.toContain("touch-pan-y");
  });
});
