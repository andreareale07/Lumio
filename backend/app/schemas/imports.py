import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

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

    model_config = {"from_attributes": True}


class ImportPreview(BaseModel):
    columns: list[str]
    sample_rows: list[list[str]]
    suggested_mapping: MappingConfig
    available_mappings: list[ImportMappingOut]


class ImportUploadResponse(BaseModel):
    import_: ImportOut = Field(alias="import")
    preview: ImportPreview

    model_config = {"populate_by_name": True}


class ImportConfirmRequest(BaseModel):
    import_mapping_id: uuid.UUID | None = None
    mapping: MappingConfig | None = None
    # Se valorizzato e la mappatura usata e' quella inline (`mapping`), la
    # persiste come nuova ImportMapping riusabile — decisione presa con
    # l'utente: mappature salvabili, non un formato fisso.
    save_as: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _exactly_one_mapping_source(self) -> Self:
        if (self.import_mapping_id is None) == (self.mapping is None):
            raise ValueError("specificare esattamente uno tra import_mapping_id e mapping")
        if self.save_as and self.import_mapping_id is not None:
            raise ValueError("save_as e' valido solo con una mappatura inline (mapping)")
        return self


class ImportDuplicateError(BaseModel):
    detail: str
    existing_import_id: uuid.UUID
    existing_status: str
