from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemSetting(Base):
    """Configurazione di ISTANZA (mai per-workspace: sono parametri operativi
    dell'infrastruttura condivisa — worker/Redis — non una scelta di un
    singolo tenant), tabella globale come `banks`/`bank_parsers`: nessuna
    RLS, nessun `workspace_id`.

    Prima applicazione: soglie di staleness per il rilevatore generico di job
    bloccati (`app/services/job_health.py`) — vedi la chiave `job_health.*`.
    Pensata per crescere in futuro in un pannello di configurazione gestibile
    da un ruolo admin di istanza (non ancora esistente, vedi
    `app/models/workspace_member.py`): per questo `value` resta un JSONB
    generico (non una colonna per tipo) e non un semplice env var, cosi' che
    un cambio non richieda il riavvio del processo (letto ad ogni uso, mai
    cache-ato come `app.core.config.get_settings()`).
    """

    __tablename__ = "system_settings"
    __mapper_args__ = {"eager_defaults": True}

    key: Mapped[str] = mapped_column(String, primary_key=True)
    # Scalare JSON grezzo (es. 420, non {"seconds": 420}): tiene semplice sia
    # il PATCH via API sia una futura UI (un solo campo numerico/booleano/
    # stringa per riga, niente da destrutturare).
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    default_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
