import shutil
from pathlib import Path, PurePosixPath


class LocalStorageProvider:
    """Implementazione filesystem locale di `StorageProvider`.

    I path relativi sono sempre costruiti dal chiamante a partire da UUID
    generati server-side (mai dal nome file originale ne' da input utente),
    quindi il path traversal e' strutturalmente impossibile — vedi
    `app/services/import_paths.py`. Qui si applica comunque una verifica
    difensiva che il path risolto resti dentro `root`.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _resolve(self, rel_path: str) -> Path:
        # PurePosixPath normalizza i separatori indipendentemente dall'OS su
        # cui gira il processo; poi si risolve contro root e si verifica il
        # contenimento, difesa in profondita' anche se il chiamante non
        # dovrebbe mai passare un path costruito da input non fidato.
        candidate = (self._root / PurePosixPath(rel_path).as_posix()).resolve()
        root_resolved = self._root.resolve()
        if root_resolved not in candidate.parents and candidate != root_resolved:
            raise ValueError(f"path {rel_path!r} escapes storage root")
        return candidate

    def save(self, rel_path: str, data: bytes) -> None:
        path = self._resolve(rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, rel_path: str) -> bytes:
        return self._resolve(rel_path).read_bytes()

    def exists(self, rel_path: str) -> bool:
        return self._resolve(rel_path).exists()

    def delete_prefix(self, rel_path_prefix: str) -> None:
        path = self._resolve(rel_path_prefix)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
