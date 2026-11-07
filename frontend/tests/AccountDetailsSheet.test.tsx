import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AccountDetailsSheet } from "../src/features/settings/open-banking/AccountDetailsSheet";
import type { BankConnectionAccount } from "../src/types/api";
import { setDesktop } from "./matchMedia";

const baseAccount: BankConnectionAccount = {
  id: "a1",
  name: "Conto Test",
  product: null,
  iban_masked: "IT60••••3456",
  currency: "EUR",
  enabled: true,
  financial_account_id: "f1",
  last_sync_at: "2026-11-07T10:00:00Z",
  transactions_imported: 12,
  last_sync_stats: {
    at: "2026-11-07T10:00:00Z",
    fetch: {
      strategy: "longest",
      date_from: null,
      pages: 2,
      raw_count: 20,
      accepted: 17,
      discarded: { zero_amount: 2, malformed: 1 },
      status_counts: { BOOK: 20 },
      sub_codes: { UPCT: 3 },
      flags: { external_id_placeholder: 4, has_counterparty_name: 10 },
      repeated_external_ids: 0,
    },
    persist: { imported: 10, known_duplicate: 5, in_review: 1, tombstoned: 1 },
  },
  balance_snapshot: { at: "2026-11-07T10:00:00Z", rows_with_balance: 10, continuity_gaps: 2 },
};

function renderSheet(account: BankConnectionAccount | null, onResync = vi.fn()) {
  render(<AccountDetailsSheet account={account} loading={false} error={null} onClose={vi.fn()} onResync={onResync} />);
  return onResync;
}

describe("AccountDetailsSheet", () => {
  it("mostra i conteggi dell'ultima lettura, i motivi di scarto e l'avviso sul saldo", () => {
    setDesktop(true);
    renderSheet(baseAccount);

    expect(screen.getByText("Movimenti letti dalla banca")).toBeInTheDocument();
    expect(screen.getByText("Importo zero")).toBeInTheDocument();
    expect(screen.getByText("Non leggibili")).toBeInTheDocument();
    expect(screen.getByText(/Il saldo dopo movimento non quadra in 2 punti/)).toBeInTheDocument();
    expect(screen.getByText(/UPCT ×3/)).toBeInTheDocument();
  });

  it("senza letture registrate lo dice e non mostra tabelle vuote", () => {
    setDesktop(true);
    renderSheet({ ...baseAccount, last_sync_stats: null, balance_snapshot: null });
    expect(screen.getByText(/Nessuna lettura registrata/)).toBeInTheDocument();
    expect(screen.queryByText("Movimenti letti dalla banca")).not.toBeInTheDocument();
  });

  it("'Rileggi storico' chiede conferma con l'avviso sui limiti prima di partire (anche su smartphone)", async () => {
    setDesktop(false);
    const user = userEvent.setup();
    const onResync = renderSheet({ ...baseAccount, balance_snapshot: null });

    await user.click(screen.getByRole("button", { name: "Rileggi storico…" }));
    expect(onResync).not.toHaveBeenCalled();
    expect(screen.getByRole("note")).toHaveTextContent(/Intesa, BPM, BPER e MPS concedono una sola lettura/);

    await user.click(screen.getByRole("button", { name: "Rileggi storico" }));
    expect(onResync).toHaveBeenCalledTimes(1);
  });

  it("mostra l'errore di un conto la cui lettura e' fallita", () => {
    setDesktop(true);
    renderSheet({ ...baseAccount, last_sync_stats: { error: "incomplete_fetch" }, balance_snapshot: null });
    expect(screen.getByRole("alert")).toHaveTextContent(/solo in parte/);
  });
});
