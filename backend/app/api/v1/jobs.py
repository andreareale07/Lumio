from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.schemas.jobs import JobOut
from app.services.job_registry import build_jobs_view

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Vista di sola LETTURA sulla pagina Impostazioni > Job: stesso principio di
# /system-settings (istanza, nessun workspace, autenticazione richiesta ma
# nessun controllo di ruolo — in attesa del futuro rework admin/utente). Il
# toggle enabled/disabled e le soglie modificabili passano dal PATCH
# generico gia' esistente su /system-settings/{key} (vedi enabled_setting_key/
# setting_key qui sotto), questo endpoint serve solo ad assemblare la vista
# leggibile per il frontend.


@router.get("", response_model=list[JobOut])
async def list_jobs(_user=Depends(get_current_user)) -> list[dict]:
    return await build_jobs_view()
