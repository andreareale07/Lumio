import type { AccountType } from "../../types/api";

export const ACCOUNT_TYPE_LABELS: Record<AccountType, string> = {
  checking: "Conto corrente",
  savings: "Conto di risparmio",
  brokerage: "Conto titoli",
  cash: "Contanti",
  credit_card: "Carta di credito",
  other: "Altro",
};
