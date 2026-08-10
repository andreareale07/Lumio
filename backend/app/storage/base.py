"""Interfaccia astratta di storage (CLAUDE.md, SPEC §85: `StorageProvider` e'
una delle interfacce che in futuro potrebbe diventare un servizio separato,
es. S3-compatible — SPEC §11).

In milestone 04 l'unico uso e' il file originale di un import
(`workspaces/<workspace_uuid>/imports/<import_uuid>/original.csv`), ma
l'interfaccia resta generica: chi la usa lavora solo con path relativi e
byte, senza conoscere se dietro c'e' il filesystem locale o altro.
"""
from typing import Protocol


class StorageProvider(Protocol):
    def save(self, rel_path: str, data: bytes) -> None:
        """Scrive `data` al path relativo, creando le directory necessarie."""
        ...

    def read(self, rel_path: str) -> bytes:
        """Legge l'intero contenuto del file al path relativo."""
        ...

    def exists(self, rel_path: str) -> bool: ...

    def delete_prefix(self, rel_path_prefix: str) -> None:
        """Rimuove ricorsivamente tutto cio' che sta sotto il prefisso (es.
        l'intera cartella di un import), usata dai test per il cleanup."""
        ...
