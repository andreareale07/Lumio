import type { TransactionType } from "../../types/api";

export const TRANSACTION_TYPE_LABELS: Record<TransactionType, string> = {
  expense: "Spesa",
  income: "Entrata",
  transfer: "Trasferimento",
  investment: "Investimento",
  dividend: "Dividendo",
  interest: "Interesse",
  fee: "Commissione",
  tax: "Tassa",
  refund: "Rimborso",
  adjustment: "Rettifica",
};
