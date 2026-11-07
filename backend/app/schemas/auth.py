import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Codice a 6 cifre, richiesto solo se l'utente ha attivato la 2FA.
    totp_code: str | None = Field(default=None, max_length=16)


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    created_at: datetime
    totp_enabled: bool = False

    model_config = {"from_attributes": True}


class MeResponse(UserOut):
    workspace_id: uuid.UUID
    # Da settings, non dal DB (milestone 10): permette al frontend di
    # nascondere nav/pagina Google Sheets senza una request che fallisce
    # quando l'istanza gira con GOOGLE_ENABLED=false.
    google_enabled: bool
    # Come google_enabled: da settings, permette al frontend di nascondere la
    # sezione Conti bancari quando l'istanza gira con OPEN_BANKING_ENABLED=false.
    open_banking_enabled: bool = False
    # Sistema di valute: letta una volta al login/refresh (stesso pattern
    # di google_enabled), cosi' ogni pagina che ne ha bisogno (default dei
    # form, picker) non deve fare una chiamata dedicata.
    base_currency: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: MeResponse
    # Solo per il client nativo (header `X-Lumio-Client: native`): niente cookie
    # nel WebView, il refresh token viaggia nel body e vive nel Keystore.
    # Per il web resta None (il token e' solo nel cookie httpOnly).
    refresh_token: str | None = None


class TotpSetupResponse(BaseModel):
    # Mostrato una sola volta, all'avvio dell'attivazione: poi non e' piu' leggibile.
    secret: str
    otpauth_uri: str


class TotpEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=16)


class TotpDisableRequest(BaseModel):
    password: str
    code: str = Field(min_length=6, max_length=16)
