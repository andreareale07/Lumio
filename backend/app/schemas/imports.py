import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.services.csv_import import MappingConfig


class ImportMappingCreate(BaseModel):
    name: str = Field(min_length=1)
    financial_account_id: uuid.UUID | None = None
    config: MappingConfig


class ImportMappingUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    financial_account_id: uuid.UUID | None = None
    config: MappingConfig | None = None


class ImportMappingOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    financial_account_id: uuid.UUID | None
    name: str
    config: MappingConfig
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImportOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    financial_account_id: uuid.UUID
    import_mapping_id: uuid.UUID | None
    mapping_config: MappingConfig | None
    # Milestone 05: 'csv' (default) o 'pdf'. bank_id/bank_parser_id sono
    # valorizzati solo per 'pdf' (rilevati all'upload).
    file_type: str
    bank_id: uuid.UUID | None
    bank_parser_id: uuid.UUID | None
    job_id: str | None
    status: str
    filename: str
    file_hash: str
    file_size: int
    period_start: date | None
    period_end: date | None
    transactions_found: int
    transactions_imported: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    # Classificazione AI disaccoppiata dal job di import (rework UX/design):
    # None finche' l'import non e' 'completed', poi pending/running/
    # completed/failed/skipped — vedi ai_classification_job.py.
    ai_classification_status: str | None
    ai_transactions_total: int
    ai_transactions_classified: int

    model_config = {"from_attributes": True}


class ImportPreview(BaseModel):
    # Popolati solo per file_type='csv' (scelta/conferma della mappatura
    # colonne). Per 'pdf' restano vuoti/None: il parser e' deterministico,
    # non c'e' nulla da mappare — vedi detected_bank_* sotto.
    columns: list[str] = Field(default_factory=list)
    sample_rows: list[list[str]] = Field(default_factory=list)
    suggested_mapping: MappingConfig | None = None
    available_mappings: list[ImportMappingOut] = Field(default_factory=list)
    # Popolati solo per file_type='pdf' (SPEC §42: stage "banca riconosciuta").
    detected_bank_code: str | None = None
    detected_bank_name: str | None = None


class ImportUploadResponse(BaseModel):
    import_: ImportOut = Field(alias="import")
    preview: ImportPreview

    model_config = {"populate_by_name": True}


class ImportConfirmRequest(BaseModel):
    # Tutti i campi sotto hanno senso solo per file_type='csv': per 'pdf' il
    # body di conferma e' vuoto (`{}`), il parser e' deterministico e non
    # richiede alcuna scelta di mappatura. La validazione "esattamente uno
    # tra import_mapping_id e mapping" per il canale csv vive nell'endpoint
    # (app/api/v1/imports.py), non qui, perche' dipende da import_row.file_type
    # che lo schema del payload non conosce.
    import_mapping_id: uuid.UUID | None = None
    mapping: MappingConfig | None = None
    # Se valorizzato e la mappatura usata e' quella inline (`mapping`), la
    # persiste come nuova ImportMapping riusabile — decisione presa con
    # l'utente: mappature salvabili, non un formato fisso.
    save_as: str | None = Field(default=None, min_length=1)


class ImportDuplicateError(BaseModel):
    detail: str
    existing_import_id: uuid.UUID
    existing_status: str


class ImportTransactionsCountOut(BaseModel):
    transactions_count: int


class ImportDeleteResult(BaseModel):
    deleted_transactions_count: int


class ImportFileContent(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    truncated: bool
    total_rows: int
