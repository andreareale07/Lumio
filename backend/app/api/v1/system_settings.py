from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.system_setting import SystemSetting
from app.schemas.system_settings import SystemSettingOut, SystemSettingUpdate

router = APIRouter(prefix="/system-settings", tags=["system-settings"])

# Configurazione di ISTANZA (tabella globale, no RLS/workspace — vedi
# app/models/system_setting.py), non di un singolo tenant: per questo qui
# basta essere autenticati (get_current_user), non serve un workspace.
#
# Nessun controllo di RUOLO oggi: qualunque utente autenticato puo' leggere
# E MODIFICARE questi valori. E' un rischio accettato esplicitamente (in
# attesa del futuro rework che introduce un ruolo admin di istanza, oggi
# inesistente — vedi app/models/workspace_member.py, "role" e' solo
# owner/member DENTRO un workspace) — su un'istanza dove piu' persone
# indipendenti si registrano, un tenant qualsiasi potrebbe oggi alterare
# soglie operative che riguardano tutti. Da chiudere quando il ruolo admin
# esistera'.


@router.get("", response_model=list[SystemSettingOut])
async def list_system_settings(
    _user=Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[SystemSetting]:
    result = await db.execute(select(SystemSetting).order_by(SystemSetting.key))
    return list(result.scalars().all())


@router.patch("/{key}", response_model=SystemSettingOut)
async def update_system_setting(
    key: str,
    payload: SystemSettingUpdate,
    _user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SystemSetting:
    setting = await db.get(SystemSetting, key)
    if setting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Configurazione non trovata")

    # Validazione minima e generica (nessuno schema per-chiave oggi): il
    # nuovo valore deve avere lo stesso tipo JSON di quello attuale, e un
    # numero non puo' diventare non-positivo — evita di rompere un
    # meccanismo che legge questo valore aspettandosi un numero di secondi.
    # `type(...) is ...`, non `isinstance`: `bool` e' sottoclasse di `int` in
    # Python, isinstance(True, int) sarebbe True e lascerebbe passare un
    # booleano su una soglia numerica.
    current_type = type(setting.value)
    if type(payload.value) is not current_type:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Il valore deve essere dello stesso tipo di quello attuale ({current_type.__name__})",
        )
    # `not isinstance(_, bool)`: stesso motivo del check sopra, un booleano
    # e' anche un int in Python (False <= 0 e' True) e non deve mai finire
    # scambiato per una soglia non positiva.
    if isinstance(payload.value, (int, float)) and not isinstance(payload.value, bool) and payload.value <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Il valore deve essere positivo")

    setting.value = payload.value
    await db.commit()
    return setting
