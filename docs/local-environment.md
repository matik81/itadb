# Audit dell'ambiente locale

Rilevazione: 23 settembre 2026, Windows 11 Pro 64 bit, build 26200. Workspace Windows.
24 processori logici; 65.939.009.536 byte RAM (circa 61,4 GiB); circa 1,49 TiB liberi su C:.
WSL2 attivo con Ubuntu e filesystem Linux quasi vuoto. Lo spazio apparente del disco WSL
è virtuale e condivide il disco fisico: non sommarlo allo spazio libero di Windows.

| Strumento | Stato iniziale verificato | Azione |
|---|---|---|
| Git Windows | 2.55.0, credential manager configurato | Già utilizzabile |
| Node.js | 24.19.0 | Già utilizzabile |
| npm | 11.17.0 | Usare npm.cmd in PowerShell |
| VS Code | Presente nel PATH | Nessuna installazione richiesta |
| WSL2 / Ubuntu | Disponibile; Python 3.14.4, Git 2.53.0 | Non riutilizzare la venv Windows qui |
| Python Windows | Solo alias Microsoft Store, nessun runtime rilevato | Python 3.13 gestito con uv |
| uv | Non presente nel PATH | Copia portabile locale preparata in .tools/uv |
| Docker / Compose | Non presenti né in Windows né in Ubuntu | Da installare per stack completo locale |
| PostgreSQL / psql | Non presenti | Forniti dal container; installazione nativa non necessaria |
| GitHub CLI | Non presente; GitHub credential già in Git | Copia portabile locale preparata in .tools/gh |
| pnpm | Non presente | Non necessario: il progetto usa npm |

## Preparato durante lo scaffold

Senza modificare installazioni globali: uv 0.12.17, GitHub CLI 2.101.0 e Python 3.13.15 in
`.tools/`, virtualenv `.venv/`, dipendenze Python e `apps/web/node_modules/`.
Queste directory sono ignorate da Git e non vengono pubblicate. I lockfile sono versionati.

La verifica TLS iniziale falliva con il trust store predefinito di Node/uv. È stata risolta
per processo tramite `NODE_USE_SYSTEM_CA=1` e `uv --system-certs`, usando le CA Windows.
Non sono state disabilitate verifiche TLS né cambiate le execution policy di PowerShell.

## Da installare per sviluppare agevolmente

1. **Docker Desktop con backend WSL2 e Compose v2**, oppure Docker Engine+Compose in Ubuntu.
   Scegliere una sola modalità e verificarla con `docker version` e `docker compose version`.
   Valutare i termini applicabili di Docker Desktop al proprio contesto.
2. **uv nel PATH**, consigliato per uso ordinario: `winget install --id astral-sh.uv -e`.
   In alternativa usare la copia locale; uv gestisce Python 3.13 per questo repository.
3. **GitHub CLI nel PATH**, consigliato: `winget install --id GitHub.cli -e` e configurare
   l'accesso interattivo quando necessario. Git già dispone di credenziali utilizzabili.

Non sono necessari PostgreSQL nativo, Redis, Java, Spark, Kubernetes o pnpm per la v0.1.
Non è stata eseguita alcuna installazione globale o di Docker durante questo lavoro.
Il controllo `scripts/doctor.ps1` permette di aggiornare l'inventario senza modifiche.
