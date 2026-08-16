import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useEtaEstimate } from "../src/lib/eta";

describe("useEtaEstimate", () => {
  it("nessuna stima senza campioni live ne' startedAt", () => {
    const { result } = renderHook(() => useEtaEstimate(5, 100));
    expect(result.current).toBeNull();
  });

  it("usa la media-da-inizio (startedAt) quando non c'e' ancora un campione live", () => {
    const now = Date.now();
    vi.spyOn(Date, "now").mockReturnValue(now);
    // 10 processate in 100 secondi -> 10s/item -> 90 rimanenti -> 900s (~15 minuti)
    const startedAt = new Date(now - 100_000).toISOString();

    const { result } = renderHook(() => useEtaEstimate(10, 100, startedAt));

    expect(result.current).not.toBeNull();
    expect(result.current!.remainingSeconds).toBeCloseTo(900, 0);

    vi.restoreAllMocks();
  });

  it("un campione live realistico prende il sopravvento sulla media-da-inizio", () => {
    let now = 1_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);
    const startedAt = new Date(now - 100_000).toISOString(); // media-da-inizio: 10s/item finora

    const { result, rerender } = renderHook(
      ({ processed }: { processed: number }) => useEtaEstimate(processed, 100, startedAt),
      { initialProps: { processed: 10 } },
    );
    expect(result.current!.remainingSeconds).toBeCloseTo(900, 0);

    // Un vero evento live, 5 secondi dopo, +1 processata: ritmo live 5s/item,
    // molto piu' veloce della media-da-inizio (10s/item) -> l'EMA lo riflette.
    now += 5_000;
    rerender({ processed: 11 });

    expect(result.current!.remainingSeconds).toBeCloseTo(89 * 5, 0);

    vi.restoreAllMocks();
  });

  it("un salto troppo ravvicinato (replay SSE) non aggiorna l'EMA, resta sulla media-da-inizio", () => {
    let now = 1_000_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);
    const startedAt = new Date(now - 100_000).toISOString();

    const { result, rerender } = renderHook(
      ({ processed }: { processed: number }) => useEtaEstimate(processed, 100, startedAt),
      { initialProps: { processed: 10 } },
    );

    // Raffica di replay: +5 processate in soli 100ms, troppo ravvicinato per essere reale.
    now += 100;
    rerender({ processed: 15 });

    // Nessuna EMA ancora: la stima resta quella "media da inizio" (ricalcolata
    // sul nuovo processed/elapsed), non quella (assurda) del replay.
    expect(result.current).not.toBeNull();
    const expectedAvgMsPerItem = 100_100 / 15;
    expect(result.current!.remainingSeconds).toBeCloseTo((85 * expectedAvgMsPerItem) / 1000, 0);

    vi.restoreAllMocks();
  });
});
