"""Elenca gli istituti a catalogo del provider Open Banking (Enable Banking)
per uno o piu' paesi, in formato tabella Markdown.

Uso (da `backend/`):

    python scripts/gen_openbanking_coverage.py \\
        --application-id <ID> --private-key-file chiave.pem --countries IT,DE

Le credenziali sono QUELLE TUE (mai condivise): l'application ID ottenuto dal
Control Panel di Enable Banking e la chiave privata corrispondente. Lo script
non scrive nulla sul DB di Lumio e non stampa mai la chiave.

L'elenco prodotto indica solo che l'istituto e' presente nel catalogo del
provider ("dichiarata dal provider"): non prova che saldi, storico o un
particolare tipo di conto funzionino. Quello si verifica con un collegamento
reale (vedi docs/open-banking-coverage.md).
"""
import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.openbanking.enable_banking import EnableBankingConnector  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--application-id", required=True)
    parser.add_argument("--private-key-file", required=True, type=Path)
    parser.add_argument("--countries", default="IT", help="Codici paese separati da virgola (default: IT)")
    args = parser.parse_args()

    connector = EnableBankingConnector(
        application_id=args.application_id,
        private_key_pem=args.private_key_file.read_text(encoding="utf-8"),
    )
    print(f"Catalogo del provider letto il {date.today().isoformat()} (livello: dichiarata dal provider)\n")
    print("| Paese | Istituto | Tipi di cliente | Consenso max (giorni) | Beta |")
    print("|---|---|---|---|---|")
    for country in (c.strip().upper() for c in args.countries.split(",") if c.strip()):
        for bank in await connector.list_institutions(country):
            days = bank.maximum_consent_validity_seconds // 86400 if bank.maximum_consent_validity_seconds else "?"
            print(
                f"| {bank.country} | {bank.name} | {', '.join(bank.psu_types) or '?'} | {days} | "
                f"{'si' if bank.beta else 'no'} |"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
