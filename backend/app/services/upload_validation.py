"""Validazione dell'upload (SPEC §53: i file caricati sono input non
affidabile, non ci si fida ne' dell'estensione ne' del Content-Type
dichiarato dal client).

Volutamente minimale per M04 (canale CSV): il sandboxing vero e proprio del
parser riguarda i PDF ed e' rimandato a M05. Qui serve solo escludere in modo
economico i casi piu' ovvi — file troppo grande, contenuto chiaramente
binario — prima di spendere tempo a provare a interpretarlo come CSV.
"""
from fastapi import HTTPException, UploadFile, status

_CHUNK_SIZE = 1024 * 1024
_BINARY_SIGNATURES = (b"%PDF", b"PK\x03\x04", b"\x89PNG", b"\xff\xd8\xff")


async def read_and_validate_csv_upload(file: UploadFile, max_size_bytes: int) -> bytes:
    """Legge l'intero upload in streaming applicando un cutoff di dimensione
    (Starlette bufferizza `UploadFile` su file temporaneo, quindi la RAM del
    processo e' comunque salva, ma senza un cutoff esplicito un file enorme
    riempirebbe il disco prima di essere mai respinto), poi verifica che il
    contenuto non sia chiaramente binario.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size_bytes:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"File troppo grande (limite {max_size_bytes} byte)",
            )
        chunks.append(chunk)
    data = b"".join(chunks)

    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "File vuoto")
    if b"\x00" in data[:_CHUNK_SIZE]:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File non riconosciuto come testo/CSV")
    if any(data.startswith(sig) for sig in _BINARY_SIGNATURES):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File non riconosciuto come testo/CSV")

    return data


def sanitize_filename(filename: str | None) -> str:
    """Nome file per il SOLO display (`imports.filename`): il path su disco
    non lo usa mai (vedi app/services/import_paths.py, costruito solo da
    UUID), quindi qui basta togliere separatori di path e caratteri di
    controllo per evitare sorprese quando viene mostrato in una UI futura.
    """
    if not filename:
        return "import.csv"
    cleaned = filename.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(ch for ch in cleaned if ch.isprintable())
    return cleaned[:255] or "import.csv"
