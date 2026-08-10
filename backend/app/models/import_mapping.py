import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImportMapping(Base):
    """Mappatura CSV colonna->campo transazione, salvabile e riusabile
    (milestone 04, decisione presa con l'utente: non un formato fisso, non
    sola euristica). Tenant-scoped a livello workspace, con un riferimento
    opzionale al conto per cui e' stata creata — vedi `Import.import_mapping_id`
    per come viene proposta automaticamente.

    `config` contiene sia la mappatura colonna->campo sia i parametri di
    parsing (delimitatore, encoding, formato data, ecc.) — vedi
    `app/services/csv_import.py:MappingConfig` per lo schema, validato da
    Pydantic al confine applicativo. JSONB e non una tabella normalizzata:
    la config e' sempre letta/scritta come un tutto, mai interrogata per
    singolo campo.
    """

    __tablename__ = "import_mappings"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_import_mappings_workspace_name"),
        # Abilita la FK composita da `imports.import_mapping_id`.
        UniqueConstraint("workspace_id", "id", name="uq_import_mappings_workspace_id"),
        # FK composita verso financial_accounts: funziona anche essendo
        # financial_account_id nullable (MATCH SIMPLE, il default, non
        # verifica il vincolo quando una colonna e' NULL) — non serve un
        # trigger qui perche' financial_accounts.workspace_id non e' MAI
        # NULL (a differenza di categories in M03, dove era la riga
        # *referenziata* ad avere workspace_id NULL).
        ForeignKeyConstraint(
            ["workspace_id", "financial_account_id"],
            ["financial_accounts.workspace_id", "financial_accounts.id"],
            ondelete="CASCADE",
            name="fk_import_mappings_workspace_account",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    financial_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
