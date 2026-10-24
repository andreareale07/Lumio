"""Ricalcolo una tantum di TUTTE le posizioni dai movimenti.

`positions` (quantita', costo medio, utile realizzato) e' un valore salvato:
si aggiorna solo quando un suo movimento cambia. Dopo una correzione al
calcolo (es. ordine dei movimenti dello stesso giorno) i valori gia' salvati
restano quelli vecchi finche' non si ricalcolano: questo script lo fa per ogni
workspace, con l'identita' RLS del suo proprietario (mai bypassando la RLS),
e stampa solo le posizioni che cambiano.

Uso: docker compose exec app python scripts/recompute_positions.py --dry-run
     docker compose exec app python scripts/recompute_positions.py
"""
import asyncio
import sys
from decimal import Decimal

from app.db.rls import rls_session
from app.services.position_service import recompute_all_positions
from app.worker.jobs.market_data import list_workspace_owners


def _fmt(value: Decimal | None) -> str:
    return "-" if value is None else f"{value:.2f}"


async def _recompute_workspace(workspace_id, owner_user_id, dry_run: bool) -> int:
    async with rls_session(owner_user_id) as db:
        changes = await recompute_all_positions(db, workspace_id)
        for c in changes:
            print(
                f"  {c.asset_name}: utile realizzato {_fmt(c.old_realized_pl)} -> {_fmt(c.new_realized_pl)}, "
                f"quantita' {_fmt(c.old_quantity)} -> {_fmt(c.new_quantity)}"
            )
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    return len(changes)


async def main() -> None:
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN: nessuna scrittura ===")

    total = 0
    for workspace_id, owner_user_id in await list_workspace_owners():
        print(f"Workspace {workspace_id}:")
        total += await _recompute_workspace(workspace_id, owner_user_id, dry_run)

    print(f"\nPosizioni {'che cambierebbero' if dry_run else 'aggiornate'}: {total}")


if __name__ == "__main__":
    asyncio.run(main())
