"""Default d'ambiente applicati PRIMA della collection di pytest.

Questo file sta nella rootdir (dove vive `pytest.ini`), non in `tests/`,
proprio per essere importato prima di `tests/conftest.py` e quindi prima che
`app.main` venga importato: `get_settings()` e' lru_cached e viene invocato
gia' all'import di `app/api/v1/router.py`, quindi un env var impostato piu'
tardi non avrebbe piu' effetto.
"""
import os
import tempfile

# `storage_path` in app/core/config.py vale /app/storage: e' il path DENTRO il
# container Docker, dove l'app gira come root su un volume dedicato. Fuori da
# Docker quel default e' una trappola silenziosa:
#   - su Linux (CI, macchine di sviluppo) il processo non e' root e non puo'
#     creare /app: gli upload degli import muoiono con PermissionError, e la
#     CI fallisce dove in locale passava;
#   - su Windows /app/storage diventa C:\app\storage, che l'ACL predefinita
#     di C:\ lascia creare a un utente normale: i test passano ma sporcano il
#     disco fuori dal repository, mascherando il problema.
# I test non hanno motivo di scrivere nel path di produzione: qui si ripiega
# su una directory temporanea, sovrascrivibile con STORAGE_PATH per chi vuole
# ispezionare i file prodotti.
os.environ.setdefault("STORAGE_PATH", os.path.join(tempfile.gettempdir(), "lumio-test-storage"))
