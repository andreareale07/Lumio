"""Convenzione dei path di storage per i file di import (SPEC §11):

    workspaces/<workspace_uuid>/imports/<import_uuid>/original.<csv|pdf>

Costruito SOLO da UUID generati server-side + `file_type` (un valore fisso
dell'enum, mai l'estensione dichiarata dal client): il nome file originale
(che e' input utente) vive esclusivamente in `imports.filename` per il
display, mai sul disco — il path traversal e' quindi strutturalmente
impossibile, non solo prevenuto a valle da una sanitizzazione del filename.
"""
import uuid


def original_file_path(workspace_id: uuid.UUID, import_id: uuid.UUID, file_type: str) -> str:
    return f"workspaces/{workspace_id}/imports/{import_id}/original.{file_type}"


def import_dir_prefix(workspace_id: uuid.UUID, import_id: uuid.UUID) -> str:
    return f"workspaces/{workspace_id}/imports/{import_id}"
