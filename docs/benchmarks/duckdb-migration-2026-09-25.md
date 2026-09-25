# Migrazione completa dell'applicazione a DuckDB — 25 settembre 2026

La consultazione v1/v2/v3 è migrata a DuckDB sul branch `feat/duckdb-serving`,
derivato da `experiment/population-storage-costs`. L'applicazione online non
richiede Neon né PostgreSQL. PostgreSQL/PostGIS rimane nel workflow locale di
preparazione e pubblicazione. Il deployment su un account cloud non è stato eseguito.

[Evidenze sintetiche JSON](duckdb-migration-2026-09-25.json),
[architettura](../architecture.md), [procedura operativa](../deployment.md),
[ADR 0017](../adr/0017-duckdb-serving.md).

## Dati effettivamente migrati

Il file completo occupa **321.400.832 byte, circa 321 MB / 306,5 MiB**.
Contiene 21 tabelle, incluse le chiavi di ordinamento testuale, e 93.386.634 righe
complessive. Queste righe includono individui, famiglie, celle e metadati; non
corrispondono a un numero di persone reali.

| Contenuto | Quantità |
|---|---:|
| Individui sintetici, completi | 58.943.464 |
| Famiglie sintetiche, complete | 26.670.169 |
| Celle derivate dai record | 3.943.689 |
| Confronti atteso/ottenuto | 3.733.338 |
| Comuni della popolazione | 7.896 |
| Province / regioni della popolazione | 107 / 20 |
| Release storiche v2, inclusa quella compatibile v1 | 4 |
| Osservazioni v2 | 22.723 |
| Confini v2 entro il budget delle API | 24.088 |
| Territori storici v2 | 24.091 |

Sono conservati provenienza, rapporto di generazione, controlli di pubblicazione,
fonti, qualità, artefatti, copertura, crosswalk e tutti i campi pubblici. La
precisione e semplificazione delle mappe corrispondono alle API precedenti.
Non viene caricata una fixture come sostituto della popolazione nazionale.

Il database PostgreSQL di origine misurato nell'esperimento occupa 17,226 GB:
l'archivio pubblico ne occupa circa il **98,1% in meno**. Non è una copia del
catalogo amministrativo, delle strutture private, degli indici, del WAL o degli
originali di preparazione. È l'insieme completo dei dati necessari alle API.
I 224 MB del primo benchmark riguardavano solo il nucleo, non il prodotto completo.

## Integrità, aggiornamento e ripristino

L'export finale è durato **86,9 secondi** in locale, con quattro thread DuckDB
e limite del motore a 2 GB. Questa non è una misura della generazione, né un
limite di risorse per il server online. Si conserva una transazione PostgreSQL
ripetibile in sola lettura per l'intera esportazione.

Per ogni tabella sono stati confrontati il numero di righe dichiarato da COPY,
i conteggi DuckDB e due fingerprint multinsieme di tutti i campi rispetto al CSV
tipizzato; sono registrati gli SHA-256 degli export e del database finale. Le
verifiche comprendono schema e tipi esatti, integrità del file e conteggi. I
fingerprint non sostituiscono l'audit scientifico originale né costituiscono firme
della fonte; quel rapporto viene conservato senza modifiche.

L'installazione crea una directory identificata dal checksum. L'attivazione
sostituisce atomicamente `current`, dopo verifica, e conserva tutte le versioni.
Il backend fissa la versione all'avvio: aggiornamento e rollback richiedono
riavvio. I test hanno verificato retry, errore di esportazione senza attivazione,
corruzione, lettori già aperti, cambio versione e ritorno alla precedente.

Un ripristino nazionale è stato eseguito in una seconda root indipendente,
ricopiando il pacchetto e verificandolo. Le richieste HTTP del test seguente
hanno utilizzato proprio questa copia ripristinata. Il backup remoto su un
servizio cloud non è stato configurato; resta un'operazione del deployment.

## Compatibilità delle API e consumo del servizio

**404 richieste** alle API reali v1/v2/v3 sono state confrontate con PostgreSQL:
tutte hanno restituito 200 e lo stesso JSON. Sono comprese mappe nazionali e
regionali, fonti, release, qualità, confini, osservazioni, crosswalk, pagine di
individui e famiglie, dettaglio e componenti, distribuzioni, validazioni e confronti.
Non è una verifica esaustiva di tutte le possibili combinazioni di filtri.

Il confronto ha individuato e risolto due differenze dei motori: conversione
TIMESTAMPTZ e ordinamento testuale. Il client DuckDB richiede `pytz`; ogni cursore
usa UTC. I ranghi testuali vengono calcolati offline secondo l'ordine PostgreSQL,
così underscore, accenti, etichette e paginazione non dipendono dalla locale
installata sul server.

Le stesse 404 risposte sono state poi verificate tramite SHA-256 del JSON
canonico attraverso HTTP in un container con **rete disabilitata**, mentre
entrambi i server PostgreSQL locali erano fermi. Il container conteneva il
backend e il client di verifica, entrambi nel medesimo limite di risorse.

| Parametro o misura | Risultato |
|---|---:|
| Budget container | 1 CPU, 512 MiB, nessuno swap aggiuntivo |
| Backend | 1 worker, 1 thread DuckDB, 4 query concorrenti |
| Limite memoria DuckDB | 256 MB |
| Client HTTP simultanei | 8 |
| Richieste completate e confrontate | 404 / 404 |
| Durata del replay | 7,59 s |
| Latenza mediana / p95 | 114 / 287 ms |
| Latenza massima | 822 ms |
| Picco memoria del cgroup, API e client inclusi | 302.411.776 byte, circa 288,4 MiB |
| OOM / processi uccisi per memoria | 0 / 0 |

È una prova locale breve e limitata, su Linux/WSL2 e Docker Desktop. Non misura
latenza Internet, carico sostenuto, cache fredda o prestazioni del provider.
Il limite del motore DuckDB da solo non rappresenta la RAM complessiva dell'app.
Sono stati inoltre eseguiti EXPLAIN ANALYZE per pagina individuale, distribuzione
nazionale e validazione comunale sullo snapshot completo.

## Applicazione e verifiche del repository

Compose ora avvia soltanto API e frontend; il profilo `offline` contiene database,
migrazioni e pipeline. Frontend, asset statici, cataloghi e mappa sono stati
richiesti attraverso Nginx con PostgreSQL fermo. Il proxy risolve periodicamente
il nome del servizio API, correggendo il problema dell'indirizzo conservato dopo
un cambio di container. Il controllo `nginx -t` è passato.

| Verifica realmente eseguita | Esito |
|---|---|
| Suite Python completa, inclusi 44 test PostgreSQL e migrazione | **353 passati**, zero saltati |
| Frontend Vitest | **43 passati** |
| Esperimento Rust: test, Clippy, formato | **3 passati**, controlli puliti |
| Ruff, formato Python, mypy | Passati |
| OpenAPI e tipi TypeScript rigenerati | Nessuna modifica al contratto |
| TypeScript, Prettier, build Vite | Passati |
| Build container API/web, Compose, healthcheck, Nginx | Passati |
| Link Markdown locali | Passati |
| Installazione dai lockfile | Passata; npm non segnala vulnerabilità note |

Restano avvisi di deprecazione già presenti in Starlette/HTTPX e Alembic; nessun
test è stato saltato. Non è stata eseguita una nuova revisione scientifica esterna
né una sessione manuale interattiva del browser. Le verifiche HTTP e i test del
frontend non equivalgono a quella revisione visiva.

## Costi e stato operativo

**La voce Neon può essere eliminata dal deployment di questa versione.** Non
rimane un residuo PostgreSQL da ospitare per storico, validazioni o geografia.
Restano il backend Railway, il suo volume, traffico, backup e l'eventuale servizio
statico del frontend. Il costo mensile effettivo dipende da utilizzo e piano:
questa prova non è una fattura né una promessa di spesa fissa.

Due copie del pacchetto occupano circa 643 MB, prima di metadati e spazio
necessario durante l'installazione. I CSV intermedi restano offline. Il processo
ha dimostrato il funzionamento nel budget di 512 MiB, inclusa la verifica HTTP;
prima del rilascio pubblico vanno misurati traffico e consumo sul servizio scelto.

`railway.json`, Dockerfile e guida di caricamento/attivazione sono predisposti.
Nessun account Neon è stato cancellato, nessun volume eliminato e nessun servizio
cloud pubblicato. I dati e le evidenze precedenti rimangono disponibili.

## Riproduzione ed evidenze locali

```sh
uv run python scripts/run_logged.py --label "Export completo" --log .tools/export.log -- uv run itadb export-serving --output NUOVA_DIRECTORY --evidence NUOVA_DIRECTORY_EVIDENZE
uv run itadb install-serving --archive NUOVA_DIRECTORY --activate
uv run python scripts/verify_serving.py --output .tools/api-parity.json
# Dopo avvio dell'API DuckDB, anche con PostgreSQL fermo:
uv run python scripts/smoke_serving.py --checks .tools/api-parity.json --url http://127.0.0.1:8000 --output .tools/http-smoke.json
```

Il confronto richiede il reader PostgreSQL locale; il replay HTTP richiede solo
l'API. Non usare il proxy Nginx con il replay concorrente senza rispettarne il
rate limit: la prova documentata usa direttamente la porta API.

Gli archivi e i CSV sono in `.tools/duckdb-migration/`, l'installazione attiva in
`data/serving/`; entrambi fuori Git. Log principali:
`.tools/duckdb-migration-export-05.log`, `duckdb-migration-parity-final.log`,
`duckdb-migration-budget.log`, `duckdb-migration-all-tests-final.log`,
`duckdb-migration-web-test.log`, `duckdb-migration-rust.log` e
`duckdb-migration-proxy.log`, tutti sotto `.tools/`. I tentativi precedenti sono
conservati: i primi due export hanno incontrato i timeout del reader, poi limitati
alla sola sessione offline. Nessuno ha attivato un archivio incompleto.
