# Esercizio e sicurezza operativa

## Sviluppo

Compose crea database PostGIS, migrazione one-shot, ruolo API, server e frontend Nginx.
`docker compose run --rm pipeline itadb ingest-demo` pubblica la fixture; ripeterlo è
idempotente. `docker compose stop` arresta i servizi; `down` rimuove i container ma conserva
i volumi. **Non usare `down -v` su dati da conservare.** Le fixture del repository sono
separate dagli originali scaricati, esclusi da Git.

Su Windows scegliere una sola modalità per virtualenv e node_modules: quella Windows
oppure quella WSL. Non riutilizzare `.venv` tra i due sistemi. Per grandi importazioni,
preferire filesystem Linux nativo in WSL o volumi Docker rispetto a `/mnt/c`.

## Confine dello scaffold

Non è un deployment pubblico di produzione. Le immagini hanno versioni di linea ma
non digest immutabili; una release produttiva deve fissare digest, scan e SBOM, oltre ai
lockfile applicativi. Il DB owner è usato per migrazione e pipeline locale; separare
DDL owner, writer e reader in produzione. Nessun TLS pubblico, secret manager, backup
automatico, tracing distribuito o sistema di allerta è provisionato qui.

## Prima esposizione pubblica

1. TLS al gateway, solo web/API esposti, DB su rete privata. CORS esplicito.
2. Segreti generati e custoditi fuori Git; rotazione e privilegi separati. Non usare le
   password di esempio. Le password nei DSN devono essere correttamente percent-encoded.
3. Rate limit condiviso a livello edge per più repliche; la zona Nginx locale non è globale.
4. Budget connessioni/CPU/RAM, timeout, queue per i batch e un solo limiter per IP upstream.
5. Log JSON con request_id e durata, metriche di errori, latenza, pool, query lente, WAL,
   spazio libero, freschezza delle fonti e run bloccati. Evitare payload o query sensibili.
6. Conservazione e recupero: backup PostgreSQL con WAL/PITR, oggetti versionati e checksum.
   Eseguire un restore su ambiente isolato e verificare release, conteggi e gate.
7. Definire RPO/RTO e retention con il gestore; nessun valore SLA è assunto nello scaffold.

## Migrazioni e recupero

Backup verificato, upgrade in staging, verifica compatibilità API, pianificazione di lock
e tempi, rollout e monitoraggio. La migrazione iniziale è intenzionalmente irreversibile:
un downgrade distruggerebbe le evidenze. Recuperare con backup verificato o migrazione
correttiva forward. Testare l'upgrade da vuoto e da ogni versione supportata.

Per file orfani confrontare `catalog.artifact` e archivio; proporre un report di garbage
collection prima della rimozione, con retention dei fallimenti. Non eliminare originali
automaticamente in caso di importazione fallita. In caso di corruzione fermare la pubblicazione,
conservare evidenza del guasto e ripristinare contenuti verificati.

La migrazione 0002 abilita `btree_gist`, aggiunge vincoli temporali e viste v2,
senza riscrivere le release pubblicate. Il ruolo di migrazione deve poter creare
l'estensione. Rieseguire `scripts/migrate.py` applica anche i grant alle nuove viste.
I test M1 creano database isolati: richiedono CREATEDB sul server **di test**.

Per la prima pubblicazione locale è stato conservato un backup pre-0002 in
`.tools/backups/itadb-before-0002-20260923.dump`, fuori Git. Il recupero consiste
nel ripristino in un nuovo database isolato e nella verifica degli artefatti,
non nel downgrade distruttivo del catalogo. Ripristinare anche la corrispondente
versione dell'applicazione quando si recupera lo schema precedente.
Il restore del backup è stato eseguito in `itadb_m1_restore_20260923` sul server
di test: schema 0001 e identità, checksum e conteggio della demo corrispondono.
Questa prova non configura un sistema automatico di backup o un obiettivo RPO/RTO.

Le acquisizioni, i manifest, i contratti e la pagina licenza della release ISTAT
sono nel volume `itadb_evidence`. Il filesystem `data/` del repository e il volume
Compose sono archivi distinti: non presumere che un file locale sia già nel container.
Non utilizzare la fixture `istat-population-invented.csv` nel catalogo applicativo:
serve esclusivamente ai test isolati. [Procedura ISTAT](sources/istat-population.md).

## Operazioni M2 e avanzamento

Le migrazioni 0003/0004 aggiungono copertura, geografie e controlli alla pubblicazione.
Prima dell'upgrade locale è stato creato e ripristinato un backup in un nuovo DB
di test; le tre release precedenti e i conteggi sono stati conservati anche dopo
due upgrade consecutivi. Il rapporto è `data/reports/m2-backup-restore.json`.
Originali e artefatti M2 sono nel volume condiviso `itadb_evidence`.

Per le attività lunghe usare `scripts/run_logged.py --label "Fase" -- COMANDO`:
output seguito in tempo reale, heartbeat ogni dieci secondi, durata e codice
finale nel log `.tools/m2-progress.log`. Non passare credenziali negli argomenti
e non registrare payload personali. Su Windows un terminale dedicato può seguire
`scripts/watch-progress.ps1`. La direttiva è anche in AGENTS.md e nelle istruzioni
generali locali di Codex.

Il benchmark `scripts/benchmark_m2.py` richiede `ITADB_TEST_DATABASE_URL`, schema
migrato e catalogo vuoto. Produce solo aggregati inventati su un server di test:
non usarlo nel catalogo applicativo. Non rimuove evidenze o database. Il rapporto
misura caricamento, query, dimensione DB, WAL e piano; non è un test di sintesi 1:1.

## GitHub

Repository pubblico `matik81/itadb`. CI su push main/PR: lint, tipi, unit, contratto OpenAPI,
test PostGIS e smoke Compose. Workflow con permessi contents:read e action fissate a SHA.
Dependabot propone aggiornamenti; audit dipendenze settimanale. Richiedere i controlli e
una revisione sulle PR, vietare force push, abilitare segnalazioni private, secret scanning
e push protection dove disponibili. Le impostazioni effettivamente applicate sono registrate
in docs/validation.md: un file YAML non prova che una protezione GitHub sia abilitata.
