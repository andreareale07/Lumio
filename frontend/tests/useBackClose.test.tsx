import { act, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Drawer } from "../src/components/ui/Drawer";

function Host({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Drawer open={open} onClose={onClose} title="Dettaglio">
      contenuto
    </Drawer>
  );
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 30));

describe("useBackClose", () => {
  it("il gesto indietro chiude l'overlay e non esce dalla pagina", async () => {
    const before = window.history.length;
    let closed = 0;
    const { rerender } = render(<Host open={false} onClose={() => (closed += 1)} />);
    rerender(<Host open onClose={() => (closed += 1)} />);
    expect(screen.getByText("contenuto")).toBeTruthy();
    expect(window.history.length).toBe(before + 1);

    act(() => window.history.back());
    await act(tick);
    expect(closed).toBe(1);
  });

  it("chiudendo da UI toglie la voce di cronologia aggiunta", async () => {
    const { rerender } = render(<Host open onClose={() => undefined} />);
    expect(window.history.state?.__ov?.length).toBe(1);
    rerender(<Host open={false} onClose={() => undefined} />);
    await act(tick);
    expect(window.history.state?.__ov ?? []).toEqual([]);
  });
});
