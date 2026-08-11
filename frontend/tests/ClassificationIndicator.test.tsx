import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ClassificationIndicator } from "../src/features/transactions/ClassificationIndicator";
import type { Classification } from "../src/types/api";

function makeClassification(overrides: Partial<Classification>): Classification {
  return {
    id: "c1",
    transaction_id: "t1",
    method: "manual",
    provider: null,
    model: null,
    category_id: "cat-1",
    score: null,
    explanation: null,
    created_by_user_id: null,
    created_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

describe("ClassificationIndicator", () => {
  it("mostra 'Non categorizzato' quando non c'è nessuna classificazione", () => {
    render(<ClassificationIndicator classification={null} />);
    expect(screen.getByText("Non categorizzato")).toBeInTheDocument();
  });

  it("mostra 'Regola' per method=rule", () => {
    render(<ClassificationIndicator classification={makeClassification({ method: "rule" })} />);
    expect(screen.getByText(/Regola/)).toBeInTheDocument();
  });

  it("mostra 'Manuale' sia per method=manual che per method=user", () => {
    const { rerender } = render(<ClassificationIndicator classification={makeClassification({ method: "manual" })} />);
    expect(screen.getByText(/Manuale/)).toBeInTheDocument();

    rerender(<ClassificationIndicator classification={makeClassification({ method: "user" })} />);
    expect(screen.getByText(/Manuale/)).toBeInTheDocument();
  });

  it("mostra il punteggio percentuale per method=ai", () => {
    render(
      <ClassificationIndicator
        classification={makeClassification({ method: "ai", score: "0.92", provider: "anthropic" })}
      />,
    );
    expect(screen.getByText(/AI 92%/)).toBeInTheDocument();
  });
});
