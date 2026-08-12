from datetime import date, datetime

from pydantic import BaseModel


class ConnectUrlOut(BaseModel):
    """Il frontend naviga il BROWSER (non un fetch) su `authorize_url`: un
    redirect diretto del backend non funzionerebbe qui, perche' l'endpoint
    e' protetto da bearer token (serve l'identita' per costruire lo
    `state`) e una navigazione reale del browser non porta con se'
    l'header Authorization (vive solo in memoria JS, mai in un cookie per
    questo scopo) — vedi `frontend/src/features/settings/integrations/api.ts`."""

    authorize_url: str


class GoogleIntegrationOut(BaseModel):
    """Mai i token: solo cio' che serve a mostrare la card "Connesso" in UI
    (SPEC_FE §50). `drive_folder_name` e' `None` quando il file vive nella
    root "Il mio Drive" (nessuna cartella scelta via Picker, stato valido)."""

    google_account_email: str
    spreadsheet_url: str
    drive_folder_name: str | None
    connected_at: datetime
    last_exported_at: datetime | None


class PickerTokenOut(BaseModel):
    """Unica eccezione deliberata alla regola "mai token dall'API": il solo
    access_token corrente (mai il refresh_token), a vita breve, per
    autorizzare il widget Google Picker lato browser — comportamento
    previsto da Google stesso per questo meccanismo."""

    access_token: str
    expires_in_seconds: int


class SetDriveFolderRequest(BaseModel):
    """`folder_id=None` riporta il file nella root "Il mio Drive"."""

    folder_id: str | None
    folder_name: str | None


class ExportRequest(BaseModel):
    date_from: date
    date_to: date
    include_portfolio: bool | None = None  # None = automatico (has_holdings)
    include_charts: bool = True


class ExportTriggered(BaseModel):
    job_id: str
