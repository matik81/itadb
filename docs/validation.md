# Verifica dello scaffold

Verifica eseguita il 23 settembre 2026. Repository pubblico:
[matik81/itadb](https://github.com/matik81/itadb).

## Controlli locali Windows

- Python 3.13.15: 24 test unitari/contratto superati; 3 test di integrazione richiedono
  PostgreSQL e sono eseguiti separatamente in GitHub.
- Ruff lint e format, mypy strict: superati.
- Generazione OpenAPI e tipi TypeScript verificata; nessuna connessione DB necessaria.
- Frontend: TypeScript, 3 test Vitest, Prettier e build Vite superati.
- npm audit: zero vulnerabilità note alla data del controllo.
- `git diff --check`: nessun errore nel diff finale.
- Generazione SQL Alembic offline: riuscita.

I test Python emettono due avvisi di deprecazione upstream (TestClient/httpx e alias
AnyIO); non sono errori applicativi. Le dipendenze sono bloccate in uv.lock e aggiornabili
tramite Dependabot. L'audit pip-audit locale non ha completato per il trust store Requests;
lo stesso controllo è stato eseguito con successo in CI Linux, senza disabilitare TLS.

## PostgreSQL e container su GitHub Actions

[CI completa passata](https://github.com/matik81/itadb/actions/runs/35795918660):
unit/contratti, frontend, migrazioni ripetute, integrazione PostgreSQL/PostGIS e smoke
Docker Compose. Il percorso di importazione demo è stato eseguito contro un DB reale;
testati idempotenza, immutabilità, privilegi reader, paginazione, rollback del gate e
pruning a una partizione. Il Compose costruisce entrambe le immagini, avvia i servizi,
importa la demo e verifica web e API attraverso Nginx.

[Audit dipendenze passato](https://github.com/matik81/itadb/actions/runs/35795812590):
pip-audit e npm audit. Questi controlli rilevano vulnerabilità conosciute nei pacchetti;
non costituiscono una revisione di sicurezza completa del prodotto.

La prima esecuzione ha individuato una compilazione errata dei `%s` nella funzione
PostgreSQL `format()`. Corretta la compilazione tramite SQLAlchemy TextClause; nuovo
upgrade da database vuoto e avvio Compose riusciti. Le correzioni sono nella cronologia.

## Prova di capacità colonnare

`uv run python scripts/benchmark.py`, 1.000.000 righe artificiali, DuckDB 1.5.5,
Windows, limite 1 GiB e 4 thread: Parquet 1.817.914 byte, scrittura circa 0,091 s,
aggregazione su 8.000 codici circa 0,008 s. Dati regolari a bassissima entropia, cache
non controllata: prova funzionale del percorso colonnare, **non** stima di produzione
o benchmark della popolazione italiana. Nessun test nazionale 1:1 è stato eseguito.

## Configurazione GitHub verificata

Repository pubblico, branch principale main, CODEOWNERS @matik81, Discussions abilitate,
cancellazione automatica dei branch dopo merge. Abilitati segnalazioni private di
vulnerabilità, Dependabot security updates, secret scanning e push protection.
Le protezioni del branch si verificano nelle impostazioni GitHub; il relativo stato
non si deduce dalla sola presenza della CI.

## Limiti della verifica

Nessun import live ISTAT/Eurostat, validazione statistica reale, test di carico concorrente,
generazione della popolazione sintetica o deploy pubblico dell'applicazione.
Nessun controllo visuale nel browser: frontend verificato con component test e build.
Docker/PostgreSQL non sono stati installati su questa macchina; i test corrispondenti
sono stati eseguiti in runner GitHub isolati. Per le installazioni locali vedere
[local-environment.md](local-environment.md).
