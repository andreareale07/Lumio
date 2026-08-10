"""Validazione dell'upload (SPEC §53: i file caricati sono input non
affidabile, non ci si fida ne' dell'estensione ne' del Content-Type
dichiarato dal client, ne' — per i PDF — che un file con estensione `.pdf`
sia davvero un PDF valido).

Due canali (milestone 04 CSV, milestone 05 PDF) condividono la lettura con
cutoff di dimensione; poi si biforcano: il CSV resta la verifica minimale
gia' vista in M04 (escludere i casi ovviamente binari), il PDF apre
davvero il file con pdfplumber sotto timeout (SPEC §53: limite dimensione +
timeout + gestione errori) per essere certi che sia interpretabile prima di
crearne una riga import — nessuna esecuzione di contenuto: si legge solo la
struttura/il testo, mai un motore JS/form (pdfplumber/pdfminer non ne hanno).
"""
import asyncio
import io

import pdfplumber
from fastapi import HTTPException, UploadFile, status

_CHUNK_SIZE = 1024 * 1024
_PDF_MAGIC = b"%PDF-"
# %PDF rimosso da qui (era in M04, quando il canale PDF non esisteva ancora
# ed era semplicemente uno dei tanti binari da respingere): un vero PDF ora
# e' un file legittimo, distinto da "non riconosciuto come testo/CSV" sotto.
_BINARY_SIGNATURES_NON_CSV = (b"PK\x03\x04", b"\x89PNG", b"\xff\xd8\xff")


async def _read_with_size_cap(file: UploadFile, max_size_bytes: int) -> bytes:
    """Legge l'intero upload in streaming applicando un cutoff di dimensione
    (Starlette bufferizza `UploadFile` su file temporaneo, quindi la RAM del
    processo e' comunque salva, ma senza un cutoff esplicito un file enorme
    riempirebbe il disco prima di essere mai respinto)."""
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
    return b"".join(chunks)


def _open_pdf_sync(data: bytes) -> None:
    """Verifica di apribilita' vera e propria (non solo i magic byte
    iniziali): PDF cifrati, troncati o con stream corrotti sollevano qui,
    non piu' avanti nel worker su un import gia' creato. Gira sotto
    `asyncio.wait_for` (vedi read_and_validate_import_upload) perche' un PDF
    patologico (bomba di decompressione, struttura ricorsiva patologica) deve
    fallire in tempo limitato, non tenere appesa la richiesta HTTP di upload."""
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if not pdf.pages:
            raise ValueError("PDF senza pagine")


async def _validate_pdf_structure(data: bytes, timeout_seconds: int) -> None:
    try:
        await asyncio.wait_for(asyncio.to_thread(_open_pdf_sync, data), timeout=timeout_seconds)
    except TimeoutError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Timeout durante la verifica del PDF"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "File non riconosciuto come PDF valido"
        ) from exc


async def read_and_validate_import_upload(
    file: UploadFile, max_size_bytes: int, pdf_open_timeout_seconds: int
) -> tuple[bytes, str]:
    """Ritorna (bytes, file_type) dove file_type e' 'csv' o 'pdf', dedotto
    dal CONTENUTO (magic byte `%PDF-`), mai dal nome/estensione dichiarati
    dal client — e' esattamente questo che rende sicuro il rifiuto di un
    file non-PDF rinominato con estensione `.pdf` (DoD milestone 05): un tale
    file non ha il magic byte, quindi qui finisce nel ramo CSV, dove la
    verifica binaria lo respinge comunque se non e' testo valido.
    """
    data = await _read_with_size_cap(file, max_size_bytes)

    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "File vuoto")

    if data.startswith(_PDF_MAGIC):
        await _validate_pdf_structure(data, pdf_open_timeout_seconds)
        return data, "pdf"

    if b"\x00" in data[:_CHUNK_SIZE]:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File non riconosciuto come testo/CSV")
    if any(data.startswith(sig) for sig in _BINARY_SIGNATURES_NON_CSV):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File non riconosciuto come testo/CSV")

    return data, "csv"


def sanitize_filename(filename: str | None) -> str:
    """Nome file per il SOLO display (`imports.filename`): il path su disco
    non lo usa mai (vedi app/services/import_paths.py, costruito solo da
    UUID), quindi qui basta togliere separatori di path e caratteri di
    controllo per evitare sorprese quando viene mostrato in una UI futura.
    """
    if not filename:
        return "import"
    cleaned = filename.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(ch for ch in cleaned if ch.isprintable())
    return cleaned[:255] or "import"
