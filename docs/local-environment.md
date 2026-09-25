# Ambiente locale

Linux, con Ubuntu/WSL2 come riferimento. Conservare clone, dati e virtualenv
nel filesystem Linux. Servono Python 3.13, uv 0.12.17, Node.js 24 e npm.
Docker Desktop con integrazione WSL è necessario soltanto per Compose.
`bash scripts/doctor.sh` verifica gli strumenti senza cambiare il sistema.

## Sviluppo

```sh
cp -n .env.example .env
uv sync --locked
npm --prefix apps/web ci
uv run itadb serve
# Secondo terminale:
npm --prefix apps/web run dev
```

Frontend: <http://localhost:5173>. API: <http://localhost:8000/docs>.
La CLI legge `.env` nella root; Vite legge `apps/web/.env.local`.
Il frontend usa `http://localhost:8000` come default di sviluppo.

## Docker

Con un archivio installato:

```sh
docker compose up --build -d --wait
```

Frontend: <http://localhost:8080>. API: <http://localhost:8080/api/docs>.
Compose avvia API e web, con archivio montato in sola lettura. Fermare l'API
avviata a mano prima di usare Compose, per liberare la porta 8000.

`itadb init-serving` è riservato a un'installazione nuova con catalogo vuoto.
Per installare i dati disponibili seguire la [guida deployment](deployment.md).

## Preparazione e test

```sh
uv run itadb prepare-spatial
uv run pytest
```

`prepare-spatial` installa l'estensione ufficiale cartografica di DuckDB, necessaria
solo al computer di preparazione e ai test geometrici. I test usano directory
DuckDB temporanee e fixture inventate; nessun database esterno va configurato.
La suite ordinaria può essere eseguita con `pytest -m "not integration"`.
I controlli completi sono nel [README](../README.md#verifiche-di-sviluppo).
