import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DETECTION_OVERRIDE_TYPES = ("recurring_series", "anomaly")
# 'confirmed' riservata ma NON usata in v1 (nessun endpoint la scrive, vedi
# `app/api/v1/analytics.py` — DetectionOverrideIn accetta solo 'ignored'):
# lo slot naturale per un futuro "questo e' un abbonamento anche se non
# l'hai rilevato automaticamente" (piano FETTA 2 §2.12).
DETECTION_OVERRIDE_DECISIONS = ("ignored", "confirmed")


class DetectionOverride(Base):
    """Correzione manuale dell'utente su un segnale di rilevazione
    ricorrenze/anomalie (piano `synchronous-chasing-pike.md` FETTA 2 §2.8),
    applicazione diretta di CLAUDE.md: "le correzioni manuali hanno sempre
    priorita' sull'AI" — qui l'inferenza e' l'algoritmo deterministico
    `recurrence_calc`/`anomaly_calc`, non un provider AI, ma il principio e'
    lo stesso: il suo fallimento dominante e' un falso positivo che l'utente
    deve poter silenziare in modo persistente.

    Esattamente un target per riga, coerente col tipo (CHECK
    `ck_detection_overrides_target`, applicato nel DB — mai solo in
    Pydantic): `series_key` per `recurring_series`, `transaction_id` per
    `anomaly`. Due indici UNIQUE PARZIALI (uno per `override_type`, vedi la
    migration 0035) invece di un unique a 4 colonne: Postgres tratta i NULL
    come distinti, un unique su colonne nullable non farebbe da vincolo.
    """

    __tablename__ = "detection_overrides"
    __table_args__ = (
        CheckConstraint(
            "override_type IN ('recurring_series', 'anomaly')", name="ck_detection_overrides_type"
        ),
        CheckConstraint("decision IN ('ignored', 'confirmed')", name="ck_detection_overrides_decision"),
        CheckConstraint(
            "(override_type = 'recurring_series' AND series_key IS NOT NULL AND transaction_id IS NULL) "
            "OR (override_type = 'anomaly' AND transaction_id IS NOT NULL AND series_key IS NULL)",
            name="ck_detection_overrides_target",
        ),
        # Nullable (soddisfatta automaticamente quando transaction_id e'
        # NULL, cioe' per le righe 'recurring_series' — stesso principio di
        # `TransactionDedupDecision.source_import_id`): un override
        # 'anomaly' punta sempre a una transazione dello STESSO workspace
        # (SPEC §57), mai verificato solo applicativamente.
        ForeignKeyConstraint(
            ["workspace_id", "transaction_id"],
            ["transactions.workspace_id", "transactions.id"],
            ondelete="CASCADE",
            name="fk_detection_overrides_workspace_transaction",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    override_type: Mapped[str] = mapped_column(String, nullable=False)
    # `series_key` e' l'hash troncato calcolato da `recurrence_calc.series_key_for`
    # (sha256[:32] esadecimale = 32 caratteri), mai una FK — le serie non
    # sono una tabella, sono calcolate on-the-fly (§2.6 del piano).
    series_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
