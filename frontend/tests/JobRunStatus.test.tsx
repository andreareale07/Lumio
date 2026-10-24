import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { JobRunStatus } from "../src/components/ui/JobRunStatus";

describe("JobRunStatus", () => {
  it("mostra 'Non ancora eseguito' quando non c'e' nessun JobRun (mai eseguito)", () => {
    render(<JobRunStatus run={null} />);
    expect(screen.getByText("Non ancora eseguito.")).toBeInTheDocument();
  });

  it("mostra lo stato 'In corso' mentre il job e' running, senza orario di fine", () => {
    render(
      <JobRunStatus
        run={{ status: "running", started_at: "2026-08-11T10:00:00Z", finished_at: null, message: null }}
      />,
    );
    expect(screen.getByText("In corso")).toBeInTheDocument();
  });

  it("mostra 'Completato' e il messaggio quando l'ultima esecuzione e' riuscita", () => {
    render(
      <JobRunStatus
        run={{
          status: "success",
          started_at: "2026-08-11T10:00:00Z",
          finished_at: "2026-08-11T10:00:05Z",
          message: "3 prezzi aggiornati su 3 asset.",
        }}
      />,
    );
    expect(screen.getByText("Completato")).toBeInTheDocument();
    expect(screen.getByText(/3 prezzi aggiornati su 3 asset\./)).toBeInTheDocument();
  });

  it("mostra 'Non riuscito' e il messaggio di errore quando l'ultima esecuzione e' fallita", () => {
    render(
      <JobRunStatus
        run={{
          status: "failed",
          started_at: "2026-08-11T10:00:00Z",
          finished_at: "2026-08-11T10:00:05Z",
          message: "provider non raggiungibile",
        }}
      />,
    );
    expect(screen.getByText("Non riuscito")).toBeInTheDocument();
    expect(screen.getByText(/provider non raggiungibile/)).toBeInTheDocument();
  });

  it("con il job in corso dentro l'app indica dove seguirlo (Attività)", () => {
    render(
      <MemoryRouter>
        <JobRunStatus run={{ status: "running", started_at: "2026-08-11T10:00:00Z", finished_at: null, message: null }} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Segui in Attività" })).toHaveAttribute("href", "/activity");
  });

  it("a job concluso non propone il link", () => {
    render(
      <MemoryRouter>
        <JobRunStatus
          run={{ status: "success", started_at: "2026-08-11T10:00:00Z", finished_at: "2026-08-11T10:00:05Z", message: null }}
        />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
