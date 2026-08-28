import { describe, expect, it } from "vitest";

import { buildDietzReturnSeries, modifiedDietzReturn } from "../src/lib/modifiedDietz";

describe("modifiedDietzReturn", () => {
  it("caso a mano verificato nel piano di sessione: posizione 1000€ a inizio anno, vendita parziale a meta' anno con guadagno realizzato, il resto continua ad apprezzarsi", () => {
    // 100 unita' comprate a 10 = 1000 di costo/valore a inizio anno (V0).
    // A meta' anno si vendono 50 unita' a 14 (guadagno realizzato
    // (14-10)*50 = 200): proceeds netti 700 lasciano il portafoglio
    // (flusso -700). Le 50 unita' restanti si apprezzano a 16 entro fine
    // anno: valore residuo 50*16 = 800 = V1.
    // Guadagno economico totale = realizzato 200 + non realizzato
    // (16-10)*50=300 -> 500, e infatti numerator = V1-V0-F =
    // 800-1000-(-700) = 500: il numeratore di Modified Dietz ritorna il
    // guadagno economico totale del periodo, indipendentemente dai pesi.
    //
    // Date scelte apposta perche' la vendita cada esattamente a meta' del
    // periodo in termini di peso: dal 2023-01-01 al 2023-12-29 sono 362
    // giorni, dal 2023-01-01 al 2023-07-01 (data della vendita) sono 181
    // giorni -> giorni residui dopo la vendita = 362-181 = 181 -> peso
    // esattamente 0.5.
    // denominatore = V0 + peso*F = 1000 + 0.5*(-700) = 650.
    // R = 500 / 650 = 0.7692307692307693 — piu' alto del "naive" 500/1000
    // (50%) perche' il capitale medio investito durante l'anno era piu'
    // basso di 1000 (il grosso prelievo di meta' anno pesa per meta' del
    // periodo) — esattamente la correzione che Modified Dietz introduce
    // rispetto a un semplice guadagno/capitale-iniziale.
    const r = modifiedDietzReturn(
      1000,
      800,
      [{ date: "2023-07-01", amount: -700 }],
      "2023-01-01",
      "2023-12-29",
    );
    expect(r).not.toBeNull();
    expect(r!).toBeCloseTo(500 / 650, 10);
  });

  it("nessun flusso: il rendimento e' la semplice variazione di valore", () => {
    const r = modifiedDietzReturn(1000, 1100, [], "2023-01-01", "2023-12-31");
    expect(r).toBeCloseTo(0.1, 10);
  });

  it("portafoglio che apre durante il periodo (V0=0): il primo flusso diventa l'inizio a peso pieno", () => {
    // Nessuna posizione a inizio periodo: il primo movimento (apertura,
    // +500) e' l'inizio effettivo del periodo, quindi ha peso 1 per
    // costruzione (e' esattamente all'inizio del periodo effettivo).
    // Fine periodo V1=550 -> guadagno 50 su un capitale investito di 500
    // -> 10%.
    const r = modifiedDietzReturn(
      0,
      550,
      [{ date: "2023-07-01", amount: 500 }],
      "2023-01-01",
      "2023-12-31",
    );
    expect(r).toBeCloseTo(0.1, 10);
  });

  it("V0=0 e nessun flusso: nessun capitale mai investito nel periodo -> null", () => {
    const r = modifiedDietzReturn(0, 0, [], "2023-01-01", "2023-12-31");
    expect(r).toBeNull();
  });

  it("flussi multipli nello stesso giorno vengono nettati prima di pesare", () => {
    const withTwoFlows = modifiedDietzReturn(
      1000,
      1200,
      [
        { date: "2023-01-01", amount: 100 },
        { date: "2023-01-01", amount: -30 },
      ],
      "2023-01-01",
      "2023-12-31",
    );
    const withNettedFlow = modifiedDietzReturn(
      1000,
      1200,
      [{ date: "2023-01-01", amount: 70 }],
      "2023-01-01",
      "2023-12-31",
    );
    expect(withTwoFlows).not.toBeNull();
    expect(withTwoFlows).toBeCloseTo(withNettedFlow!, 10);
  });

  it("denominatore zero (capitale netto investito nullo dopo i pesi) -> null, mai un'infinita'", () => {
    // Vendita totale (-100) proprio all'inizio del periodo (peso 1): il
    // denominatore V0 + peso*F = 100 + 1*(-100) = 0.
    const r = modifiedDietzReturn(100, 0, [{ date: "2023-01-01", amount: -100 }], "2023-01-01", "2023-12-31");
    expect(r).toBeNull();
  });
});

describe("buildDietzReturnSeries", () => {
  it("un versamento a meta' serie non appare come guadagno: il punto appena dopo resta a 0%", () => {
    // Stesso scenario segnalato dall'utente: 1000 all'inizio, poi un
    // versamento di 500 che porta il valore a 1500 senza alcun movimento
    // di prezzo reale — il punto del versamento e quello subito dopo
    // devono restare a 0%, non salire a +50%.
    const points = [
      { period: "2023-01-01", label: "1 gen", value: 1000 },
      { period: "2023-02-01", label: "1 feb", value: 1000 },
      { period: "2023-03-01", label: "1 mar", value: 1500 },
      { period: "2023-04-01", label: "1 apr", value: 1500 },
    ];
    const flows = [{ date: "2023-03-01", amount: 500 }];
    const series = buildDietzReturnSeries(points, flows, "2023-01-01");
    expect(series.map((p) => p.value)).toEqual([0, 0, 0, 0]);
  });

  it("un vero apprezzamento di prezzo, senza flussi, produce un rendimento cumulato crescente", () => {
    const points = [
      { period: "2023-01-01", label: "1 gen", value: 1000 },
      { period: "2023-04-01", label: "1 apr", value: 1050 },
      { period: "2023-07-01", label: "1 lug", value: 1100 },
    ];
    const series = buildDietzReturnSeries(points, [], "2023-01-01");
    expect(series[0]!.value).toBeCloseTo(0, 10);
    expect(series[1]!.value).toBeCloseTo(0.05, 10);
    expect(series[2]!.value).toBeCloseTo(0.1, 10);
  });

  it("l'ultimo punto della serie coincide con modifiedDietzReturn calcolato direttamente su inizio/fine range", () => {
    const points = [
      { period: "2023-01-01", label: "1 gen", value: 0 },
      { period: "2023-07-01", label: "1 lug", value: 500 },
      { period: "2023-12-31", label: "31 dic", value: 550 },
    ];
    const flows = [{ date: "2023-07-01", amount: 500 }];
    const series = buildDietzReturnSeries(points, flows, "2023-01-01");
    const direct = modifiedDietzReturn(0, 550, flows, "2023-01-01", "2023-12-31");
    expect(series[series.length - 1]!.value).toBeCloseTo(direct!, 10);
  });

  it("i punti prima del primo flusso (nessun capitale investito) sono omessi, non mostrati come 0%", () => {
    const points = [
      { period: "2022-06-01", label: "giu", value: 0 },
      { period: "2022-09-01", label: "set", value: 0 },
      { period: "2023-01-01", label: "gen", value: 1000 },
    ];
    const flows = [{ date: "2023-01-01", amount: 1000 }];
    const series = buildDietzReturnSeries(points, flows, "2022-06-01");
    expect(series.map((p) => p.period)).toEqual(["2023-01-01"]);
  });

  it("nessun punto -> serie vuota", () => {
    expect(buildDietzReturnSeries([], [], "2023-01-01")).toEqual([]);
  });
});
