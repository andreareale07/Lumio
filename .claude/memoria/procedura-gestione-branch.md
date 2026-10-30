# Procedura: git, branch e commit

## Branch
- Si lavora **direttamente su `master`**. Nessun branch di feature, nessuna PR, nessun merge.
- Remote: `origin` = `github.com/andreareale07/Lumio` (la CI gira a ogni push).
- I worktree degli agenti (`.claude/worktrees/agent-*`, branch `worktree-agent-*`) sono
  temporanei: non vanno usati come base di lavoro. Non rimuoverli senza ok dell'utente.

## Quando chiedere conferma
- **Commit: solo su richiesta esplicita dell'utente.** Mai un commit automatico a fine
  fetta.
- **Push: mai senza richiesta esplicita.**
- Distruttivi (`reset --hard`, `checkout --`, `clean`, `branch -D`, rimozione di worktree):
  sempre chiedere prima.

## Formato del commit
- In italiano, con apostrofo al posto delle accentate (`attivita'`, `e'`).
- Titolo: `tipo(scope): descrizione` - tipi in uso: `feat`, `fix`, `test`; scope di dominio
  (`ux`, `ai`, `portfolio`, `parser`, `maintenance`, `ci`...).
- Corpo: il **perche'** e il comportamento visibile, elenco puntato se ci sono piu' parti;
  citare migration nuove (`Migration 0043`) e scelte non ovvie.
- **Mai la riga `Co-Authored-By`** (richiesta dell'utente del 2026-10-30; i commit
  precedenti la contengono, quelli nuovi no).
- Un commit per fetta coerente. Quando i file sono intrecciati tra piu' fette si accetta un
  commit cumulativo, ma va segnalato all'utente prima di farlo.
- Prima di `git add` controllare `git status`: non includere `Lumio.tar.gz`, file di
  debug o modifiche non correlate di altre sessioni.
