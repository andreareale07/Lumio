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


class UserOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MeResponse(UserOut):
    workspace_id: uuid.UUID
    # Da settings, non dal DB (milestone 10): permette al frontend di
    # nascondere nav/pagina Google Sheets senza una request che fallisce
    # quando l'istanza gira con GOOGLE_ENABLED=false.
    google_enabled: bool
    # Sistema di valute: letta una volta al login/refresh (stesso pattern
    # di google_enabled), cosi' ogni pagina che ne ha bisogno (default dei
    # form, picker) non deve fare una chiamata dedicata.
    base_currency: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: MeResponse
