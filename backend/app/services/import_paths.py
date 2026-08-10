"""Convenzione dei path di storage per i file di import (SPEC §11):

    workspaces/<workspace_uuid>/imports/<import_uuid>/original.csv

Costruito SOLO da UUID generati server-side: il nome file originale (che e'
input utente) vive esclusivamente in `imports.filename` per il display, mai
sul disco — il path traversal e' quindi strutturalmente impossibile, non
solo prevenuto a valle da una sanitizzazione del filename.
"""
import uuid


def original_file_path(workspace_id: uuid.UUID, import_id: uuid.UUID) -> str:
    return f"workspaces/{workspace_id}/imports/{import_id}/original.csv"


def import_dir_prefix(workspace_id: uuid.UUID, import_id: uuid.UUID) -> str:
    return f"workspaces/{workspace_id}/imports/{import_id}"
