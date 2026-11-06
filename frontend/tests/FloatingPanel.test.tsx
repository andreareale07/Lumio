import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FloatingPanel } from "../src/components/ui/FloatingPanel";

function renderPanel() {
  const anchor = document.createElement("button");
  document.body.appendChild(anchor);
  return render(
    <FloatingPanel open anchorRef={{ current: anchor }} onClose={() => {}}>
      <div>contenuto</div>
    </FloatingPanel>,
  );
}

describe("FloatingPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sposta a destra un pannello che esce dal bordo sinistro dello schermo", () => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      left: -20,
      right: 300,
      top: 0,
      bottom: 100,
      width: 320,
      height: 100,
      x: -20,
      y: 0,
      toJSON: () => ({}),
    });
    renderPanel();

    expect(screen.getByText("contenuto").parentElement?.style.transform).toContain("translateX(28px)");
  });

  it("non sposta un pannello che sta gia' dentro lo schermo", () => {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      left: 100,
      right: 400,
      top: 0,
      bottom: 100,
      width: 300,
      height: 100,
      x: 100,
      y: 0,
      toJSON: () => ({}),
    });
    renderPanel();

    expect(screen.getByText("contenuto").parentElement?.style.transform).toContain("translateX(0px)");
  });
});
