/** Un solo parser registrato oggi (`app/parsers/__init__.py:PARSERS`) —
 * mappa aggiungere una voce quando ne arriva un altro (SPEC §17: nuova
 * banca -> nuovo parser_type). Fallback sul valore grezzo se un
 * parser_type non e' ancora in questa mappa, mai una stringa vuota. */
export const PARSER_TYPE_LABELS: Record<string, string> = {
  trade_republic_pdf: "Trade Republic",
};

export function parserTypeLabel(parserType: string): string {
  return PARSER_TYPE_LABELS[parserType] ?? parserType;
}
