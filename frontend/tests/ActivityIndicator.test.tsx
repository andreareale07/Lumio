import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ActivityIndicator } from "../src/features/activity/ActivityIndicator";
import type { ActivityItem } from "../src/features/activity/api";

function renderIndicator() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ActivityIndicator />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function item(overrides: Partial<ActivityItem>): ActivityItem {
  return {
    kind: "reclassification",
    label: "reclassification",
    label_key: "reclassification.name",
    status: "running",
    events_url: "/classification/reclassify/events",
    cancel_url: null,
    started_at: "2026-10-24T14:09:00Z",
    finished_at: null,
    message: null,
    processed: 120,
    total: 400,
    ...overrides,
  };
}

function stubActivity(items: ActivityItem[]) {
  const fetchMock = vi.fn<typeof fetch>(
    async () => new Response(JSON.stringify({ items }), { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ActivityIndicator", () => {
  it("segnala quante elaborazioni sono in corso e le elenca con l'avanzamento", async () => {
    stubActivity([item({}), item({ kind: "snapshot_backfill", label_key: "snapshotBackfill.name", processed: null, total: null })]);
    renderIndicator();

    const button = await screen.findByRole("button", { name: "2 elaborazioni in corso" });
    await userEvent.click(button);

    expect(screen.getByText("120/400")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Apri Attività" })).toHaveAttribute("href", "/activity");
    expect(screen.getAllByRole("progressbar")).toHaveLength(2);
  });

  it("senza nulla in corso lo dice e non mostra barre di avanzamento", async () => {
    stubActivity([item({ status: "success", processed: null, total: null })]);
    renderIndicator();

    const button = await screen.findByRole("button", { name: "Nessuna elaborazione in corso" });
    await userEvent.click(button);

    expect(screen.getByText("Nessuna elaborazione in corso.")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("evidenzia le elaborazioni fallite di recente", async () => {
    stubActivity([item({ status: "failed", processed: null, total: null })]);
    renderIndicator();

    expect(await screen.findByRole("button", { name: "1 elaborazione fallita di recente" })).toBeInTheDocument();
  });

  it("si chiude con Escape", async () => {
    stubActivity([item({})]);
    renderIndicator();

    await userEvent.click(await screen.findByRole("button", { name: "1 elaborazione in corso" }));
    expect(screen.getByRole("dialog", { name: "Elaborazioni" })).toBeInTheDocument();

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Elaborazioni" })).not.toBeInTheDocument();
  });

  it("offre Interrompi per le attività che lo permettono e lo chiede al server", async () => {
    const fetchMock = stubActivity([item({ cancel_url: "/classification/reclassify/cancel" })]);
    renderIndicator();

    await userEvent.click(await screen.findByRole("button", { name: "1 elaborazione in corso" }));
    await userEvent.click(screen.getByRole("button", { name: "Interrompi" }));

    expect(await screen.findByRole("button", { name: "Interruzione in corso…" })).toBeDisabled();
    const posted = fetchMock.mock.calls.some(
      ([input, init]) =>
        String(input).endsWith("/classification/reclassify/cancel") && (init as RequestInit | undefined)?.method === "POST",
    );
    expect(posted).toBe(true);
  });

  it("non mostra Interrompi per le attività che non si possono fermare", async () => {
    stubActivity([item({ cancel_url: null })]);
    renderIndicator();

    await userEvent.click(await screen.findByRole("button", { name: "1 elaborazione in corso" }));
    expect(screen.queryByRole("button", { name: "Interrompi" })).not.toBeInTheDocument();
  });
});
