# Registro delle verifiche

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

## Limiti della verifica iniziale dello scaffold

La verifica iniziale dello scaffold non comprendeva import live ISTAT/Eurostat,
validazione statistica reale, test di carico concorrente, generazione della popolazione
sintetica o deploy pubblico dell'applicazione. Il primo campione live è descritto sotto.
Nessun controllo visuale nel browser: frontend verificato con component test e build.
Docker/PostgreSQL non sono stati installati su questa macchina; i test corrispondenti
sono stati eseguiti in runner GitHub isolati. Per le installazioni locali vedere
[local-environment.md](local-environment.md).

## Primo onboarding ISTAT, 23 settembre 2026

Incremento successivo allo scaffold nella stessa giornata:

- `uv sync --locked`, Ruff lint/format e mypy: superati.
- **75 test Python unitari/contratto superati**; 3 test PostgreSQL esclusi con
  `-m "not integration"`. Restano i due avvisi upstream descritti sopra.
- Baseline frontend rieseguita: typecheck, 3 test Vitest e build superati.
  Nessuna modifica al frontend, alle dipendenze o al contratto OpenAPI.
- Acquisizioni live ISTAT selettive: dataflow, DSD/codelist e CSV di 21 osservazioni
  (20 regioni e Italia) per il 1° gennaio 2024. Licenza e metadati conservati.
- Controllo CLI sul campione ufficiale: tutti i gate passati, somma regionale e
  totale nazionale pari a 58.971.230; campione di quattro righe revisionato tra
  risposta originale e rapporto. Non è un confronto statistico tra fonti indipendenti.
- Seconda esecuzione offline sugli stessi input: stesso percorso, SHA-256 e data
  di modifica del rapporto. Nei test, dati invalidi producono quarantena senza
  rapporto di successo; evidenze modificate non vengono sovrascritte.
- `git diff --check`: superato. Nessun originale acquisito incluso in Git;
  fixture numerica inventata e metadati ridotti con attribuzione separata.

Rapporto locale di questa verifica:
`data/reports/istat-population-84c0e35d-1064-5215-b85c-4e2502643c9b.json`.
Il nome dipende dagli input e dai manifest di acquisizione, non è un ID di release.
[Procedura, hash, licenza e limiti](sources/istat-population.md).

Nessuna pubblicazione ufficiale in DB/API/web, nessuna migrazione e nessun test di
integrazione PostgreSQL eseguito in questo primo incremento. La pubblicazione
successiva, descritta sotto, completa il [piano](plans/m1-istat-population.md).

## Pubblicazione ISTAT locale, 23 settembre 2026

Secondo incremento, con Docker Desktop disponibile e PostgreSQL 17.5/PostGIS 3.5
in container. I test usano un server separato dallo stack applicativo.

- **90 test Python superati: 77 unitari/contratto e 13 di integrazione PostgreSQL**,
  nessun test saltato nell'esecuzione completa. Ruff lint/format e mypy superati.
  Restano avvisi upstream TestClient/httpx, AnyIO e configurazione Alembic.
- Frontend: typecheck, **4 test Vitest**, Prettier e build Vite superati.
  OpenAPI esportata e tipi TypeScript rigenerati; route e schemi di risposta v1
  confrontati con la versione precedente e identici.
- Migrazione 0002 verificata da database vuoto, ripetuta e applicata a una demo
  già pubblicata. Testati privilegi reader, vincoli territoriali e temporali,
  revisione con predecessore esplicito, idempotenza e concorrenza, rifiuto di fork,
  mancata pubblicazione per dati invalidi, artefatti mancanti, gate falliti e
  rollback dopo COPY. Nessuna migrazione applicata riscritta.
- Piano di query su **20.000 righe artificiali**: una partizione, accesso tramite
  indice e pagina di 51 righe. Un'esecuzione ha misurato 1,249 ms di pianificazione
  e 0,294 ms di esecuzione; cache non controllata, nessuna stima nazionale.
  Evidenza: `data/reports/m1-query-plan-25c89092-e119-4c74-af39-0e2c9f387a87.json`.
- Backup pre-0002 conservato in `.tools/backups/itadb-before-0002-20260923.dump`.
  **Restore realmente eseguito** nel database isolato `itadb_m1_restore_20260923`:
  versione schema 0001, ID, checksum originale e conteggio della demo verificati.
- Stack locale ricostruito e avviato, migrazione applicata e originali ISTAT
  pubblicati nel catalogo applicativo. Ripetere l'import riusa la stessa release.
  Archivio originale, metadati, licenza e rapporti nel volume `itadb_evidence`.
- Verifica HTTP attraverso Nginx: tutte le **21 osservazioni e i quattro attributi
  upstream** coincidono con il CSV acquisito, anche paginando a 7 righe. Totale
  regionale 58.971.230, **72 controlli qualità passati e 12 artefatti registrati**.
  Readiness positiva; v1 continua a mostrare la demo e non espone le release v2.
- Verifica visiva con Chrome headless a 1440 px e 600 px; evidenze in
  `data/reports/m1-web-final-desktop.png` e `data/reports/m1-web-narrow.png`.
  Nessuna verifica interattiva completa o su dispositivo mobile fisico.

Release corrente: `eaef6df9-96db-58bd-9b9d-9e203d89d030`, successiva a
`4d602369-9057-57a0-9942-9d0ac9bcb91e`. La revisione rende portabili i checksum
dei contratti tra Windows e Linux (terminatori LF); tutti i valori statistici
sono invariati e la prima release resta consultabile. Rapporto di verifica HTTP:
`data/reports/m1-publication-eaef6df9-96db-58bd-9b9d-9e203d89d030.json`.

M1 è completata per il solo snapshot regionale del 1° gennaio 2024. Non sono
stati eseguiti un deploy pubblico, una nuova CI remota di queste modifiche,
una validazione statistica indipendente o un benchmark nazionale. La data di
pubblicazione upstream rimane non accertata; gli stati senza flag non sono
convertiti in dati osservati. Storia territoriale e altri periodi restano in M2.
